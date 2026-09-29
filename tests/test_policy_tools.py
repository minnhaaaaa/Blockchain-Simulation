import io
import tempfile
import unittest
import uuid
from pathlib import Path

from agentguard.artifacts import ArtifactStore
from agentguard.policy import PolicyEvaluator
from agentguard.schema_validation import SchemaValidator
from agentguard.tools import ToolContext, ToolError, default_registry


ROOT=Path(__file__).resolve().parents[1]


class PolicyToolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.schemas=SchemaValidator(ROOT/"contracts"/"schemas"); self.evaluator=PolicyEvaluator(self.schemas,100,10)
        self.store=ArtifactStore(self.root/"artifacts",1024*1024); self.tools=default_registry(100,100); self.job=str(uuid.uuid4())
        ref=self.store.store("room","input.csv","text/csv",io.BytesIO(b"name,value\na,1\nb,2\n")); self.store.bind("room",[ref["artifact_id"]],self.job); self.ref=ref
    def tearDown(self): self.temp.cleanup()
    def policy(self,effect="allow"):
        return {"schema_version":1,"policy_id":str(uuid.uuid4()),"job_id":self.job,"owner_public_key":"x"*80,
          "rules":[{"rule_id":str(uuid.uuid4()),"tool_id":"artifact.hash","effect":effect,
          "read_artifact_ids":[self.ref["artifact_id"]],"write_scopes":[],"argument_constraints":{"type":"object"}}],
          "limits":{"max_actions":2,"max_runtime_ms_per_action":1000,"max_output_bytes_per_action":1000},"created_at_ms":1}
    def test_deny_by_default_and_explicit_policy(self):
        action={"tool_id":"unknown","input_artifact_ids":[],"arguments":{}}
        self.assertEqual("deny",self.evaluator.evaluate(self.policy(),action,[],2).decision)
        action={"tool_id":"artifact.hash","input_artifact_ids":[self.ref["artifact_id"]],"arguments":{"artifact_id":self.ref["artifact_id"]}}
        self.assertEqual("allow",self.evaluator.evaluate(self.policy(),action,[],2).decision)
        self.assertEqual("deny",self.evaluator.evaluate(self.policy("deny"),action,[],2).decision)
    def test_csv_import_and_read_only_sql(self):
        context=ToolContext("room",self.job,self.root/"workspace",self.store)
        imported=self.tools.get("csv.import_sqlite").execute(context,{"artifact_id":self.ref["artifact_id"],"table_name":"records"},[self.ref["artifact_id"]])
        self.assertEqual(2,imported["value"]["row_count"])
        result=self.tools.get("sql.query_readonly").execute(context,{"query":"SELECT name,value FROM records ORDER BY name","max_rows":10},[])
        self.assertEqual([["a","1"],["b","2"]],[list(row) for row in result["value"]["rows"]])
        with self.assertRaises((ToolError,Exception)):
            self.tools.get("sql.query_readonly").execute(context,{"query":"DELETE FROM records","max_rows":10},[])
    def test_artifact_scope_and_integrity(self):
        with self.assertRaises(Exception):
            self.store.store("../escape","bad","text/plain",io.BytesIO(b"bad"))
        row=self.store._row("room",self.ref["artifact_id"])
        (self.store.root/row["storage_path"]).write_bytes(b"tampered")
        with self.assertRaises(Exception): self.store.read("room",self.job,self.ref["artifact_id"])
