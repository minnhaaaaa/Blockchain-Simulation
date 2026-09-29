import tempfile
import unittest
import uuid
from pathlib import Path

from agentguard.canonical import encode_signature, signing_bytes
from agentguard.identity import EcdsaSigner, fingerprint
from agentguard.schema_validation import SchemaValidator
from signalling.registry import RegistryError, RoomExists, RoomRegistry
from signalling.app import create_app
from agentguard.config import SignallingConfig


ROOT=Path(__file__).resolve().parents[1]


class SignallingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.now=100000
        self.schemas=SchemaValidator(ROOT/"contracts"/"schemas")
        self.registry=RoomRegistry(Path(self.temp.name)/"rooms.sqlite3",1000,self.schemas,lambda:self.now)
        self.signer=EcdsaSigner.generate()
    def tearDown(self): self.temp.cleanup()
    def manifest(self,room="room-one"):
        value={"schema_version":1,"room_id":room,"protocol_version":"1","consensus":{"type":"pos","parameters":{
          "epoch_ms":100,"max_clock_skew_ms":0,"finality_depth":1,"max_connections":2,"block_reward":0,"minimum_stake":1}},
          "genesis":{"block_id":str(uuid.uuid4()),"created_at_ms":self.now,"allocations":[{"public_key":self.signer.public_key_pem,"amount":1,"stake":1}]},
          "creator_public_key":self.signer.public_key_pem,"created_at_ms":self.now}
        value["signature"]=encode_signature(self.signer.sign(signing_bytes("agentguard.room-manifest.v1",value,"signature"))); return value
    def join(self,room,node=None):
        return self.registry.join(room,{"schema_version":1,"node_id":node or str(uuid.uuid4()),"name":"node",
          "advertised_host":"127.0.0.1","advertised_port":1234,"public_key_fingerprint":fingerprint(self.signer.public_key_pem)})
    def test_room_is_immutable_and_signature_verified(self):
        manifest=self.manifest(); self.registry.create_room(manifest); self.assertEqual(manifest,self.registry.create_room(manifest))
        changed=dict(manifest); changed["protocol_version"]="2"
        with self.assertRaises(RoomExists): self.registry.create_room(changed)
        bad=self.manifest("room-bad"); bad["created_at_ms"]+=1
        with self.assertRaises(RegistryError): self.registry.create_room(bad)
    def test_signed_unaffordable_stake_is_rejected(self):
        invalid=self.manifest("room-invalid-stake")
        invalid["genesis"]["allocations"][0]["stake"]=2
        invalid["signature"]=encode_signature(self.signer.sign(signing_bytes("agentguard.room-manifest.v1",invalid,"signature")))
        with self.assertRaises(RegistryError): self.registry.create_room(invalid)
    def test_members_are_room_isolated_and_expire(self):
        self.registry.create_room(self.manifest("room-a")); self.registry.create_room(self.manifest("room-b"))
        member=self.join("room-a"); self.assertEqual(1,len(self.registry.list_members("room-a")["items"]))
        self.assertEqual([],self.registry.list_members("room-b")["items"])
        self.now+=1001; self.assertEqual([],self.registry.list_members("room-a")["items"])
        self.assertEqual(member["joined_at_ms"],100000)
    def test_http_contract_and_error_envelope(self):
        config=SignallingConfig("127.0.0.1",1234,Path(self.temp.name)/"unused.sqlite3",1000,100000)
        client=create_app(config,self.registry).test_client(); manifest=self.manifest()
        self.assertEqual(201,client.post("/api/rooms",json=manifest).status_code)
        missing=client.get("/api/rooms/missing-room")
        self.assertEqual(404,missing.status_code); self.assertEqual("ROOM_NOT_FOUND",missing.get_json()["code"])
        self.assertEqual(missing.headers["X-Request-ID"],missing.get_json()["request_id"])
        malformed=client.post("/api/rooms",data="{",content_type="application/json")
        self.assertEqual(422,malformed.status_code); self.assertEqual("VALIDATION_FAILED",malformed.get_json()["code"])
