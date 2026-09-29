import time
import uuid

from flask import Flask, g, has_request_context, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import BadRequest

from agentguard.artifacts import ArtifactError, ArtifactStore
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
               room_session:RoomSessionCoordinator) -> Flask:
    app=Flask(__name__); app.config["MAX_CONTENT_LENGTH"]=config.upload_limit_bytes
    CORS(app,origins=list(config.allowed_origins))
    room_session.add_listener(lambda manifest,_members:setattr(runtime,"room_id",manifest["room_id"]))

    @app.before_request
    def assign_request_id(): g.request_id=str(uuid.uuid4())
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

    @app.post("/api/room-session")
    def configure_room(): return jsonify(room_session.configure(request.get_json(force=True)))

    @app.get("/api/status")
    def status():
        chain=node.get_chain_summary(1); peers=node.get_peer_summaries(); provider_items=providers.public()
        provider_state="unconfigured" if not provider_items else ("configured" if any(x["state"]=="ready" for x in provider_items) else "unavailable")
        return jsonify({"room_id":runtime.room_id,"node_id":config.node_id,"node_name":config.node_name,
          "node_public_key_fingerprint":fingerprint(runtime.signer.public_key_pem),"node_state":"online","api_state":"online",
          "provider_state":provider_state,"chain_height":chain["height"],"finalized_height":chain["finalized_height"],
          "updated_at_ms":int(time.time()*1000)})

    @app.get("/api/providers")
    def list_providers(): return jsonify({"items":providers.public()})
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
    def create_job(): return jsonify(runtime.create_job(request.get_json(force=True)).to_dict()),202
    @app.get("/api/jobs")
    def jobs(): return jsonify({"items":projections.list_jobs(runtime.room_id,request.args.get("status"))})
    @app.get("/api/jobs/<job_id>")
    def job(job_id): return jsonify({"job":projections.projection(job_id),"events":projections.events(job_id)})
    @app.post("/api/jobs/<job_id>/accept")
    def accept(job_id): return jsonify(runtime.accept(job_id).to_dict()),202
    @app.post("/api/jobs/<job_id>/run")
    def run(job_id): runtime.run(job_id); return jsonify({"run_id":str(uuid.uuid4()),"job_id":job_id,"state":"started"}),202
    @app.post("/api/jobs/<job_id>/complete")
    def complete(job_id): return jsonify(runtime.complete(job_id,request.get_json(force=True)).to_dict()),202
    @app.post("/api/jobs/<job_id>/actions")
    def action(job_id): return jsonify(runtime.propose(job_id,request.get_json(force=True)).to_dict()),202
    @app.post("/api/jobs/<job_id>/actions/<action_id>/decision")
    def decision(job_id,action_id): return jsonify(runtime.decide(job_id,action_id,request.get_json(force=True)).to_dict()),202
    @app.get("/api/violations")
    def violations(): return jsonify({"items":projections.violations(runtime.room_id)})
    return app
