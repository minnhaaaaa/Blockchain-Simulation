import hashlib
import json
import time
import uuid
from pathlib import Path

from agentguard.artifacts import ArtifactStore
from agentguard.canonical import encode_signature, sha256_hex, signing_bytes
from agentguard.identity import Signer
from agentguard.node_service import NodeService, Submission
from agentguard.policy import PolicyEvaluator
from agentguard.projection import ProjectionStore
from agentguard.providers import ProviderRegistry
from agentguard.schema_validation import SchemaValidator
from agentguard.tools import ToolContext, ToolRegistry


class RuntimeError(ValueError): pass


class AgentRuntime:
    def __init__(self,room_id:str,data_root:Path,signer:Signer,node:NodeService,schemas:SchemaValidator,
                 artifacts:ArtifactStore,policy:PolicyEvaluator,tools:ToolRegistry,providers:ProviderRegistry,
                 projections:ProjectionStore,clock_ms=None):
        self.room_id=room_id; self.data_root=Path(data_root); self.signer=signer; self.node=node; self.schemas=schemas
        self.artifacts=artifacts; self.policy=policy; self.tools=tools; self.providers=providers; self.projections=projections
        self.clock_ms=clock_ms or (lambda:int(time.time()*1000))
        self._cancel_subscription=self.node.subscribe_state_changes(self._on_state_change)

    def _on_state_change(self,change:dict):
        state=change.get("ledger_state")
        if state == "rejected":
            self.projections.remove(change.get("event_id"))
            return
        event=self.node.get_event(change.get("event_id"))
        if event and state in ("submitted","included","finalized"):
            self.projections.apply(event,state)

    def close(self): self._cancel_subscription()

    def rebuild_from_node(self,room_id:str):
        events = self.node.list_all_events()
        with_states = [(event,self.node.get_event_state(event["event_id"])) for event in events]
        self.projections.rebuild_room(room_id,with_states)

    def _events(self,job_id): return self.projections.events_for_room(self.room_id,job_id)
    def _event(self,event_type,job_id,payload):
        events=self._events(job_id); sequence=len(events); previous=events[-1]["event_hash"] if events else None
        event={"schema_version":1,"event_id":str(uuid.uuid4()),"event_type":event_type,"room_id":self.room_id,
          "job_id":job_id,"actor_public_key":self.signer.public_key_pem,"sequence":sequence,
          "created_at_ms":self.clock_ms(),"previous_event_hash":previous,"payload":payload}
        raw=signing_bytes("agentguard.agent-event.v1",event,"event_hash","signature")
        event["event_hash"]=sha256_hex(raw); event["signature"]=encode_signature(self.signer.sign(raw))
        self.schemas.validate_named("agent-event.schema.json",event)
        submission=self.node.submit_event(event)
        if submission.ledger_state!="rejected": self.projections.apply(event,submission.ledger_state)
        return submission

    def create_job(self,request:dict):
        self.schemas.validate_named("job-create-request.schema.json",request)
        self.providers.get(request["provider_id"])
        self.policy.validate_complexity(request["policy"])
        allowed_artifacts=set(request["input_artifact_ids"])
        if any(not set(rule["read_artifact_ids"]).issubset(allowed_artifacts) for rule in request["policy"]["rules"]):
            raise RuntimeError("policy refers to an artifact outside the job")
        job_id=str(uuid.uuid4()); now=self.clock_ms(); refs=self.artifacts.bind(self.room_id,request["input_artifact_ids"],job_id)
        rules=[{"rule_id":str(uuid.uuid4()),**rule} for rule in request["policy"]["rules"]]
        policy={"schema_version":1,"policy_id":str(uuid.uuid4()),"job_id":job_id,
          "owner_public_key":self.signer.public_key_pem,"rules":rules,"limits":request["policy"]["limits"],
          "created_at_ms":now,"expires_at_ms":request["policy"].get("expires_at_ms")}
        job={"schema_version":1,"job_id":job_id,"room_id":self.room_id,"owner_public_key":self.signer.public_key_pem,
          "title":request["title"],"instructions":request["instructions"],"provider_id":request["provider_id"],
          "input_artifacts":refs,"policy":policy,"created_at_ms":now,"expires_at_ms":request["policy"].get("expires_at_ms")}
        self.schemas.validate_named("job.schema.json",job); return self._event("job.created",job_id,job)

    def accept(self,job_id):
        job=self._source_job(job_id)
        if job.get("expires_at_ms") is not None and self.clock_ms()>=job["expires_at_ms"]: raise RuntimeError("job has expired")
        if self.projections.projection(job_id,self.room_id)["status"]!="submitted": raise RuntimeError("job cannot be accepted")
        return self._event("job.accepted",job_id,{"schema_version":1,"job_id":job_id,"worker_public_key":self.signer.public_key_pem,"accepted_at_ms":self.clock_ms()})

    def _source_job(self,job_id): return self._events(job_id)[0]["payload"]
    def propose(self,job_id,action):
        if self.projections.projection(job_id,self.room_id)["status"] not in ("accepted","running"): raise RuntimeError("job is not executable")
        self.schemas.validate_named("action.schema.json",action)
        job=self._source_job(job_id)
        if job.get("expires_at_ms") is not None and self.clock_ms()>=job["expires_at_ms"]: raise RuntimeError("job has expired")
        if self.projections.projection(job_id,self.room_id)["action_count"] >= job["policy"]["limits"]["max_actions"]:
            raise RuntimeError("job action limit reached")
        if action["action_sequence"] != self.projections.projection(job_id,self.room_id)["action_count"]:
            raise RuntimeError("action sequence is not the next expected value")
        acceptance=next((event for event in self._events(job_id) if event["event_type"]=="job.accepted"),None)
        if not acceptance or acceptance["payload"]["worker_public_key"]!=self.signer.public_key_pem:
            raise RuntimeError("only the accepted worker may propose actions")
        if action["job_id"]!=job_id or action["proposer_public_key"]!=self.signer.public_key_pem: raise RuntimeError("action identity mismatch")
        self._event("action.proposed",job_id,action)
        tool=self.tools.get(action["tool_id"]); writes=tool.write_scopes(action["arguments"])
        decision=self.policy.evaluate(job["policy"],action,writes,self.clock_ms())
        payload={"schema_version":1,"decision_id":str(uuid.uuid4()),"job_id":job_id,"action_id":action["action_id"],
          "decision":decision.decision,"basis":"policy","decided_by_public_key":self.signer.public_key_pem,
          "reason_code":decision.reason_code,"reason":decision.reason,"policy_hash":self.policy.hash(job["policy"]),"decided_at_ms":self.clock_ms()}
        event_name={"allow":"action.allowed","deny":"action.denied","approval_required":"action.approval_required"}[decision.decision]
        submission=self._event(event_name,job_id,payload)
        if decision.decision=="allow": self._execute(job_id,action,tool)
        elif decision.decision=="deny": self._violation(job_id,action,"policy",decision.reason_code,decision.reason)
        return submission

    def decide(self,job_id,action_id,request):
        self.schemas.validate_named("action-decision-request.schema.json",request)
        if self._source_job(job_id)["owner_public_key"] != self.signer.public_key_pem:
            raise RuntimeError("only the job owner may decide an action")
        events=self._events(job_id); action=next((e["payload"] for e in events if e["event_type"]=="action.proposed" and e["payload"]["action_id"]==action_id),None)
        if not action: raise RuntimeError("action does not exist")
        pending=any(e["event_type"]=="action.approval_required" and e["payload"]["action_id"]==action_id for e in events)
        decided=any(e["event_type"] in ("action.approved","action.rejected") and e["payload"]["action_id"]==action_id for e in events)
        if not pending or decided: raise RuntimeError("action is not awaiting a decision")
        job=self._source_job(job_id); payload={"schema_version":1,"decision_id":str(uuid.uuid4()),"job_id":job_id,"action_id":action_id,
          "decision":request["decision"],"basis":"human","decided_by_public_key":self.signer.public_key_pem,
          "reason_code":"OWNER_DECISION","reason":request.get("reason") or "Job owner decision.",
          "policy_hash":self.policy.hash(job["policy"]),"decided_at_ms":self.clock_ms()}
        submission=self._event("action.approved" if request["decision"]=="approved" else "action.rejected",job_id,payload)
        if request["decision"]=="approved": self._execute(job_id,action,self.tools.get(action["tool_id"]))
        return submission

    def _execute(self,job_id,action,tool):
        started=self.clock_ms(); context=ToolContext(self.room_id,job_id,self.data_root/self.room_id/job_id,self.artifacts)
        try: result=tool.execute(context,action["arguments"],action["input_artifact_ids"]); status="success"; error=None
        except Exception as exc: result={"value":None,"artifacts":[]}; status="failure"; error={"code":"TOOL_FAILED","message":str(exc)}
        completed=self.clock_ms(); limits=self._source_job(job_id)["policy"]["limits"]
        encoded_output=json.dumps({"value":result["value"],"artifacts":result["artifacts"]},sort_keys=True,separators=(",",":"),default=list).encode()
        if completed-started > limits["max_runtime_ms_per_action"]:
            status="failure"; error={"code":"TOOL_TIMEOUT","message":"tool exceeded the policy runtime limit"}; result={"value":None,"artifacts":[]}; encoded_output=b"null"
        if len(encoded_output) > limits["max_output_bytes_per_action"]:
            status="failure"; error={"code":"OUTPUT_LIMIT","message":"tool output exceeded the policy size limit"}; result={"value":None,"artifacts":[]}; encoded_output=b"null"
        request_hash=sha256_hex(json.dumps(action,sort_keys=True,separators=(",",":")).encode())
        output_hash=sha256_hex(encoded_output)
        receipt={"schema_version":1,"receipt_id":str(uuid.uuid4()),"job_id":job_id,"action_id":action["action_id"],
          "worker_public_key":self.signer.public_key_pem,"tool_id":tool.tool_id,"tool_version":tool.version,
          "request_hash":request_hash,"output_hash":output_hash,"output_artifacts":result["artifacts"],"status":status,
          "error":error,"started_at_ms":started,"completed_at_ms":completed}
        receipt["signature"]=encode_signature(self.signer.sign(signing_bytes("agentguard.receipt.v1",receipt,"signature")))
        self._event("action.completed",job_id,receipt)

    def _violation(self,job_id,action,category,code,message):
        evidence=sha256_hex(json.dumps(action,sort_keys=True,separators=(",",":")).encode())
        payload={"schema_version":1,"violation_id":str(uuid.uuid4()),"job_id":job_id,"action_id":action.get("action_id"),
          "category":category,"reason_code":code,"message":message,"evidence_hash":evidence,"detected_at_ms":self.clock_ms()}
        self._event("security.violation",job_id,payload)

    def run(self,job_id):
        job=self._source_job(job_id); provider=self.providers.get(job["provider_id"])
        action=provider.propose(job,self._events(job_id),self.tools.public()); return self.propose(job_id,action)

    def complete(self,job_id,request):
        self.schemas.validate_named("job-complete-request.schema.json",request)
        events=self._events(job_id); projection=self.projections.projection(job_id,self.room_id)
        if projection["status"] not in ("accepted","running"): raise RuntimeError("job cannot be completed in its current state")
        if projection["pending_approval_count"]: raise RuntimeError("job has an action awaiting approval")
        proposed={event["payload"]["action_id"] for event in events if event["event_type"]=="action.proposed"}
        terminal={event["payload"]["action_id"] for event in events if event["event_type"] in ("action.denied","action.rejected","action.completed")}
        if proposed-terminal: raise RuntimeError("job has non-terminal actions")
        refs=[]
        for artifact_id in request["output_artifact_ids"]:
            refs.append(self.artifacts.reference_for_job(self.room_id,job_id,artifact_id))
        payload={"schema_version":1,"job_id":job_id,"status":"completed","output_artifacts":refs,
                 "summary":request["summary"],"error":None,"completed_at_ms":self.clock_ms()}
        return self._event("job.completed",job_id,payload)
