import time
import uuid
import io
import threading

from flask import Flask, g, has_request_context, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.exceptions import BadRequest

from agentguard.artifacts import ArtifactError, ArtifactStore
from agentguard.auth import OperatorAuth
from agentguard.config import ApplicationConfig
from agentguard.identity import fingerprint
from agentguard.node_service import NodeService, NodeUnavailable, SubmissionRejected
from agentguard.projection import ProjectionError, ProjectionStore
from agentguard.providers import ProviderError, ProviderRegistry
from agentguard.room_session import RoomSessionCoordinator, RoomSessionError
from agentguard.schema_validation import SchemaValidationError
from agentguard.tools import ToolError, ToolRegistry
from agentguard.worker import AgentRuntime, RuntimeError as AgentRuntimeError


def api_error(code,message,status,details=None):
    request_id=getattr(g,"request_id",None) if has_request_context() else None
    body={"code":code,"message":message,"request_id":request_id or str(uuid.uuid4())}
    if details: body["details"]=details
    return jsonify(body),status


def create_app(config:ApplicationConfig,runtime:AgentRuntime,node:NodeService,artifacts:ArtifactStore,
               projections:ProjectionStore,providers:ProviderRegistry,tools:ToolRegistry,
               room_session:RoomSessionCoordinator, auth:OperatorAuth) -> Flask:
    app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=config.upload_limit_bytes
    CORS(app,origins=list(config.allowed_origins), expose_headers=["X-Request-ID"])
    command_lock = threading.RLock()
    room_session.add_listener(lambda manifest,_members:setattr(runtime,"room_id",manifest["room_id"]))

    @app.before_request
    def assign_request_id():
        g.request_id=str(uuid.uuid4())
        if request.method == "OPTIONS" or request.path in ("/health", "/api/auth/login"):
            return None
        if request.path.startswith("/api/"):
            g.token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if not auth.valid(g.token):
                return api_error("AUTH_REQUIRED", "Sign in to this node to continue.", 401)
            if request.method != "GET":
                command_lock.acquire()
                g.command_locked = True

    @app.teardown_request
    def release_command(_error):
        if getattr(g, "command_locked", False): command_lock.release()
    @app.after_request
    def expose_request_id(response): response.headers["X-Request-ID"]=g.request_id; return response

    @app.errorhandler(SchemaValidationError)
    def schema_error(exc): return api_error("VALIDATION_FAILED",str(exc),422)
    def invalid_resource(exc): return api_error("VALIDATION_FAILED",str(exc),422)
    def missing(exc): return api_error("RESOURCE_NOT_FOUND",str(exc),404)
    def conflict(exc): return api_error("INVALID_TRANSITION",str(exc),409)
    def unavailable(exc): return api_error("NODE_UNAVAILABLE",str(exc),503)
    for error in (ArtifactError,ToolError): app.register_error_handler(error,invalid_resource)
    app.register_error_handler(ProjectionError,missing)
    for error in (AgentRuntimeError,ProviderError,SubmissionRejected): app.register_error_handler(error,conflict)
    for error in (NodeUnavailable,RoomSessionError): app.register_error_handler(error,unavailable)
    @app.errorhandler(413)
    def too_large(_): return api_error("PAYLOAD_TOO_LARGE","request exceeds configured limit",413)
    @app.errorhandler(BadRequest)
    def bad_request(exc): return api_error("VALIDATION_FAILED","request body is not valid JSON",422)

    @app.get("/health")
    def health(): return jsonify({"status":"ok"})

    @app.post("/api/auth/login")
    def login():
        body=request.get_json(force=True)
        session=auth.login(body.get("access_key") if isinstance(body,dict) else None)
        if session is None: return api_error("INVALID_ACCESS_KEY", "The node access key is incorrect.", 401)
        return jsonify({**session,"node_id":config.node_id,"node_name":config.node_name})

    @app.post("/api/auth/logout")
    def logout():
        auth.logout(g.token)
        return "",204

    @app.get("/api/identity")
    def identity():
        return jsonify({"node_id":config.node_id,"node_name":config.node_name,
                        "public_key":runtime.signer.public_key_pem})

    @app.get("/api/room-session")
    def current_room(): return jsonify({"manifest":room_session.active_manifest})

    @app.post("/api/room-session")
    def configure_room(): return jsonify(room_session.configure(request.get_json(force=True)))

    @app.get("/api/status")
    def status():
        chain=node.get_chain_summary(1); peers=node.get_peer_summaries(); provider_items=providers.public()
        provider_state="unconfigured" if not provider_items else ("configured" if any(x["state"]=="ready" for x in provider_items) else "unavailable")
        return jsonify({"room_id":runtime.room_id,"node_id":config.node_id,"node_name":config.node_name,
          "node_public_key_fingerprint":fingerprint(runtime.signer.public_key_pem),
          "node_state":"starting" if not chain["blocks"] and chain["height"] == 0 else "online","api_state":"online",
          "provider_state":provider_state,"chain_height":chain["height"],"finalized_height":chain["finalized_height"],
          "updated_at_ms":int(time.time()*1000)})

    @app.get("/api/providers")
    def list_providers(): return jsonify({"items":providers.public()})
    @app.post("/api/prompt-jobs")
    def prompt_job():
        body = request.get_json(force=True)
        runtime.schemas.validate_named("prompt-job-request.schema.json", body)
        instructions = body.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise SchemaValidationError("$.instructions", "Enter a task")
        provider = providers.get(body.get("provider_id"))
        if provider.kind != "openai_compatible":
            raise ProviderError("Prompt tasks require a configured AI agent")
        settings = provider.settings()
        limits = settings.get("job_limits")
        runtime.schemas.validate_fragment({"$ref": "policy.schema.json#/$defs/limits"}, limits)
        inputs = body.get("input_artifact_ids", [])
        rules = [{"tool_id": tool["tool_id"], "effect": "approval_required" if tool["write_scopes"] else "allow",
                  "read_artifact_ids": inputs, "write_scopes": tool["write_scopes"], "argument_constraints": {}}
                 for tool in tools.public()]
        submission = runtime.create_job({"title": instructions.strip().splitlines()[0][:160],
            "instructions": instructions.strip(), "provider_id": provider.provider_id, "input_artifact_ids": inputs,
            "policy": {"rules": rules, "limits": limits}})
        event = node.get_event(submission.event_id)
        return jsonify({**submission.to_dict(), "job_id": event["job_id"]}), 202
    @app.get("/api/tools")
    def list_tools(): return jsonify({"items":tools.public()})
    @app.get("/api/peers")
    def list_peers(): return jsonify({"items":node.get_peer_summaries()})
    @app.get("/api/chain")
    def chain():
        try: limit=int(request.args.get("limit",50))
        except ValueError: return api_error("VALIDATION_FAILED","limit must be an integer",422)
        if not 1<=limit<=200: return api_error("VALIDATION_FAILED","limit must be between 1 and 200",422)
        return jsonify(node.get_chain_summary(limit))
    @app.get("/api/chain/<block_id>")
    def block(block_id):
        value=node.get_block(block_id)
        if value is None: return api_error("RESOURCE_NOT_FOUND","block does not exist",404)
        return jsonify(value)
    @app.get("/api/stakes")
    def stakes(): return jsonify(node.get_stake_snapshot())

    @app.post("/api/artifacts")
    def upload():
        if "file" not in request.files: return api_error("VALIDATION_FAILED","file is required",422)
        item=request.files["file"]
        return jsonify(artifacts.store(runtime.room_id,item.filename or "artifact",item.mimetype or "application/octet-stream",item.stream)),201

    @app.post("/api/jobs")
    def create_job():
        submission=runtime.create_job(request.get_json(force=True))
        event=node.get_event(submission.event_id)
        return jsonify({**submission.to_dict(),"job_id":event["job_id"]}),202
    @app.get("/api/jobs")
    def jobs(): return jsonify({"items":projections.list_jobs(runtime.room_id,request.args.get("status"))})
    @app.get("/api/jobs/<job_id>")
    def job(job_id):
        projection = projections.projection(job_id, runtime.room_id)
        events=projections.events_for_room(runtime.room_id,job_id)
        scopes={e["payload"]["action_id"]:tools.get(e["payload"]["tool_id"]).write_scopes(e["payload"]["arguments"])
                for e in events if e["event_type"]=="action.proposed"}
        return jsonify({"job":projection,"events":events,"action_scopes":scopes,
                        "event_states":projections.event_states(job_id)})

    @app.get("/api/jobs/<job_id>/artifacts/<artifact_id>")
    def download(job_id,artifact_id):
        projections.projection(job_id,runtime.room_id)
        ref=artifacts.reference_for_job(runtime.room_id,job_id,artifact_id)
        content=artifacts.read(runtime.room_id,job_id,artifact_id)
        return send_file(io.BytesIO(content),mimetype=ref["media_type"],as_attachment=True,download_name=ref["name"])

    @app.post("/api/jobs/<job_id>/manual-actions")
    def manual_action(job_id): return jsonify(runtime.propose_manual(job_id,request.get_json(force=True)).to_dict()),202
    @app.post("/api/jobs/<job_id>/accept")
    def accept(job_id): return jsonify(runtime.accept(job_id).to_dict()),202
    @app.post("/api/jobs/<job_id>/run")
    def run(job_id):
        runtime.run(job_id)
        state = projections.projection(job_id, runtime.room_id)["status"]
        return jsonify({"run_id":str(uuid.uuid4()),"job_id":job_id,"state":state}),202
    @app.post("/api/jobs/<job_id>/complete")
    def complete(job_id): return jsonify(runtime.complete(job_id,request.get_json(force=True)).to_dict()),202
    @app.post("/api/jobs/<job_id>/actions")
    def action(job_id): return jsonify(runtime.propose(job_id,request.get_json(force=True)).to_dict()),202
    @app.post("/api/jobs/<job_id>/actions/<action_id>/decision")
    def decision(job_id,action_id): return jsonify(runtime.decide(job_id,action_id,request.get_json(force=True)).to_dict()),202
    @app.get("/api/violations")
    def violations(): return jsonify({"items":projections.violations(runtime.room_id)})
    return app
