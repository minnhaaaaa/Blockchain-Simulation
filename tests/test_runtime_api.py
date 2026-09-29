import io
import tempfile
import unittest
import uuid
from pathlib import Path

from agentguard.artifacts import ArtifactStore
from agentguard.config import ApplicationConfig
from agentguard.identity import EcdsaSigner
from agentguard.policy import PolicyEvaluator
from agentguard.projection import ProjectionStore
from agentguard.providers import ManualProvider, ProviderRegistry
from agentguard.room_session import RoomSessionCoordinator
from agentguard.schema_validation import SchemaValidator
from agentguard.tools import default_registry
from agentguard.worker import AgentRuntime
from api.app import create_app
from signalling.registry import RoomRegistry
from tests.fakes import MemoryNodeService, RegistryClient


ROOT=Path(__file__).resolve().parents[1]


class RuntimeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name); self.room="runtime-room"; self.node_id=str(uuid.uuid4())
        self.schemas=SchemaValidator(ROOT/"contracts"/"schemas"); self.signer=EcdsaSigner.generate(); self.node=MemoryNodeService()
        self.artifacts=ArtifactStore(root/"artifacts",100000); self.projections=ProjectionStore(root/"projection.sqlite3")
        self.providers=ProviderRegistry([ManualProvider("manual-runtime","Manual runtime")]); self.tools=default_registry(100,100)
        self.runtime=AgentRuntime(self.room,root/"work",self.signer,self.node,self.schemas,self.artifacts,PolicyEvaluator(self.schemas,100,10),self.tools,self.providers,self.projections,lambda:1000+len(self.node.events))
        registry=RoomRegistry(root/"rooms.sqlite3",1000,self.schemas,lambda:1000)
        session=RoomSessionCoordinator(RegistryClient(registry),self.schemas,self.signer,self.node_id,"node","127.0.0.1",9000,lambda:1000)
        config=ApplicationConfig("127.0.0.1",8000,root,self.room,self.node_id,"node","127.0.0.1",9000,"http://signal",100000,("http://ui",))
        self.client=create_app(config,self.runtime,self.node,self.artifacts,self.projections,self.providers,self.tools,session).test_client()
    def tearDown(self): self.temp.cleanup()
    def create_job(self,effect="allow"):
        upload=self.client.post("/api/artifacts",data={"file":(io.BytesIO(b"hello"),"input.txt")},content_type="multipart/form-data")
        artifact=upload.get_json(); constraint={"type":"object","additionalProperties":False,"required":["artifact_id"],"properties":{"artifact_id":{"type":"string","format":"uuid"}}}
        body={"title":"Runtime task","instructions":"Hash the uploaded input.","provider_id":"manual-runtime","input_artifact_ids":[artifact["artifact_id"]],
          "policy":{"rules":[{"tool_id":"artifact.hash","effect":effect,"read_artifact_ids":[artifact["artifact_id"]],"write_scopes":[],"argument_constraints":constraint}],
          "limits":{"max_actions":2,"max_runtime_ms_per_action":1000,"max_output_bytes_per_action":10000}}}
        response=self.client.post("/api/jobs",json=body); self.assertEqual(202,response.status_code,response.get_data(as_text=True))
        event_id=response.get_json()["event_id"]
        return self.node.events[event_id]["job_id"],artifact["artifact_id"]
    def test_honest_job_and_denied_action(self):
        job_id,artifact_id=self.create_job(); self.assertEqual(202,self.client.post(f"/api/jobs/{job_id}/accept").status_code)
        action={"schema_version":1,"action_id":str(uuid.uuid4()),"job_id":job_id,"action_sequence":0,"tool_id":"artifact.hash",
          "arguments":{"artifact_id":artifact_id},"input_artifact_ids":[artifact_id],"expected_output_kind":"json",
          "proposer_public_key":self.signer.public_key_pem,"proposed_at_ms":1002}
        response=self.client.post(f"/api/jobs/{job_id}/actions",json=action); self.assertEqual(202,response.status_code,response.get_data(as_text=True))
        detail=self.client.get(f"/api/jobs/{job_id}").get_json(); kinds=[e["event_type"] for e in detail["events"]]
        self.assertEqual(["job.created","job.accepted","action.proposed","action.allowed","action.completed"],kinds)
        completed=self.client.post(f"/api/jobs/{job_id}/complete",json={"summary":"Hashing completed.","output_artifact_ids":[]})
        self.assertEqual(202,completed.status_code,completed.get_data(as_text=True))
        self.assertEqual("completed",self.client.get(f"/api/jobs/{job_id}").get_json()["job"]["status"])
        denied_job,_=self.create_job("deny"); self.client.post(f"/api/jobs/{denied_job}/accept")
        action.update({"action_id":str(uuid.uuid4()),"job_id":denied_job,"proposed_at_ms":1010})
        self.client.post(f"/api/jobs/{denied_job}/actions",json=action)
        violations=self.client.get("/api/violations").get_json()["items"]; self.assertEqual(1,len(violations)); self.assertEqual("policy",violations[0]["category"])
    def test_room_session_create(self):
        body={"operation":"create","room_id":"created-room","protocol_version":"1","consensus_parameters":{
          "epoch_ms":100,"max_clock_skew_ms":0,"finality_depth":1,"max_connections":2,"block_reward":0,"minimum_stake":1},
          "genesis_allocations":[{"public_key":self.signer.public_key_pem,"amount":1}]}
        response=self.client.post("/api/room-session",json=body); self.assertEqual(200,response.status_code,response.get_data(as_text=True)); self.assertEqual("created-room",response.get_json()["room_id"])
    def test_approval_executes_once(self):
        body={"title":"Report task","instructions":"Write a reviewed report.","provider_id":"manual-runtime","input_artifact_ids":[],
          "policy":{"rules":[{"tool_id":"report.write","effect":"approval_required","read_artifact_ids":[],"write_scopes":["job.outputs"],
          "argument_constraints":{"type":"object"}}],"limits":{"max_actions":1,"max_runtime_ms_per_action":1000,"max_output_bytes_per_action":10000}}}
        created=self.client.post("/api/jobs",json=body).get_json(); job_id=self.node.events[created["event_id"]]["job_id"]
        self.client.post(f"/api/jobs/{job_id}/accept")
        action_id=str(uuid.uuid4()); action={"schema_version":1,"action_id":action_id,"job_id":job_id,"action_sequence":0,"tool_id":"report.write",
          "arguments":{"name":"report.txt","format":"text","content":"reviewed"},"input_artifact_ids":[],"expected_output_kind":"artifact",
          "proposer_public_key":self.signer.public_key_pem,"proposed_at_ms":1002}
        self.assertEqual(202,self.client.post(f"/api/jobs/{job_id}/actions",json=action).status_code)
        before=[e["event_type"] for e in self.client.get(f"/api/jobs/{job_id}").get_json()["events"]]
        self.assertEqual("action.approval_required",before[-1])
        decision=self.client.post(f"/api/jobs/{job_id}/actions/{action_id}/decision",json={"decision":"approved","reason":"Reviewed."})
        self.assertEqual(202,decision.status_code,decision.get_data(as_text=True))
        replay=self.client.post(f"/api/jobs/{job_id}/actions/{action_id}/decision",json={"decision":"approved"})
        self.assertEqual(409,replay.status_code)
        after=[e["event_type"] for e in self.client.get(f"/api/jobs/{job_id}").get_json()["events"]]
        self.assertEqual(1,after.count("action.completed"))
