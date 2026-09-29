"""
Developer 2's runtime/API test-suite, unchanged, run against the real PoS
adapter instead of MemoryNodeService. The room is created through the real
RoomSessionCoordinator + signalling registry, which drives the node's room
transition.
"""
import tempfile
import uuid
from pathlib import Path

from agentguard.artifacts import ArtifactStore
from agentguard.config import ApplicationConfig
from agentguard.policy import PolicyEvaluator
from agentguard.projection import ProjectionStore
from agentguard.providers import ManualProvider, ProviderRegistry
from agentguard.room_session import RoomSessionCoordinator
from agentguard.schema_validation import SchemaValidator
from agentguard.tools import default_registry
from agentguard.worker import AgentRuntime
from api.app import create_app
from consensus.pos.runtime import PosNodeRuntime, load_or_create_signer
from signalling.registry import RoomRegistry
from tests.fakes import RegistryClient
from tests.test_runtime_api import ROOT, RuntimeApiTests as _Dev2Suite
from tests.test_runtime_api import RuntimeApiTests
import unittest


class _EventsView:
    """`node.events[event_id]` / `len(node.events)` as the Dev 2 tests use it, read from the real ledger."""

    def __init__(self, service):
        self.service = service

    def __getitem__(self, event_id):
        event = self.service.get_event(event_id)
        if event is None:
            raise KeyError(event_id)
        return event

    def __len__(self):
        peer = self.service._peer_provider()
        if peer is None:
            return 0
        return len(peer.ledger.events_by_id) + len(peer.event_pool)


class RealAdapterRuntimeApiTests(RuntimeApiTests):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.room = "runtime-room"
        self.node_id = str(uuid.uuid4())
        self.schemas = SchemaValidator(ROOT / "contracts" / "schemas")
        self.signer = load_or_create_signer(str(root / "data"), self.node_id)
        # the state holder is filled below; the clock is the same one Developer 2's runtime uses
        holder = {}
        clock = lambda: 1000 + len(holder["view"])
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]
        self.node_runtime = PosNodeRuntime(
            data_root=str(root / "data"), node_id=self.node_id, node_name="node", bind_host="127.0.0.1", bind_port=self.port,
            signer=self.signer, max_event_bytes=200_000, connect_timeout_s=3, transition_timeout_s=15, clock_ms=clock)
        self.real = self.node_runtime.service
        self.real.events = holder["view"] = _EventsView(self.real)
        self.node = self.real
        self.artifacts = ArtifactStore(root / "artifacts", 100000)
        self.projections = ProjectionStore(root / "projection.sqlite3")
        self.providers = ProviderRegistry([ManualProvider("manual-runtime", "Manual runtime")])
        self.tools = default_registry(100, 100)
        self.runtime = AgentRuntime(self.room, root / "work", self.signer, self.node, self.schemas, self.artifacts,
                                    PolicyEvaluator(self.schemas, 100, 10), self.tools, self.providers, self.projections, clock)
        registry = RoomRegistry(root / "rooms.sqlite3", 1000, self.schemas, lambda: 1000)
        session = RoomSessionCoordinator(RegistryClient(registry), self.schemas, self.signer, self.node_id, "node",
                                         "127.0.0.1", self.port, lambda: 1000, on_verified_room=self.node_runtime.on_verified_room)
        config = ApplicationConfig("127.0.0.1", 8000, root, self.room, self.node_id, "node", "127.0.0.1", self.port,
                                   "http://signal", 100000, ("http://ui",))
        self.app = create_app(config, self.runtime, self.node, self.artifacts, self.projections, self.providers, self.tools, session)
        self.client = self.app.test_client()
        # a real, verified room: created through the coordinator, applied by the node before it returns
        session.configure({"operation": "create", "room_id": self.room, "protocol_version": "1",
                           "consensus_parameters": {"epoch_ms": 500, "max_clock_skew_ms": 5000, "finality_depth": 2,
                                                    "max_connections": 4, "block_reward": 0, "minimum_stake": 1},
                           "genesis_allocations": [{"public_key": self.signer.public_key_pem, "amount": 1000}]})

    def tearDown(self):
        self.runtime.close()
        self.node_runtime.stop()
        self.temp.cleanup()

    def test_events_are_really_in_the_ledger(self):
        job_id, _ = self.create_job()
        self.assertEqual(202, self.client.post(f"/api/jobs/{job_id}/accept").status_code)
        events = self.real.list_job_events(job_id)
        self.assertEqual(["job.created", "job.accepted"], [e["event_type"] for e in events])
        self.assertTrue(all(self.real.get_event_state(e["event_id"]) == "submitted" for e in events))
        self.assertEqual("runtime-room", self.client.get("/api/status").get_json()["room_id"])


# unittest would also re-collect the imported base class; keep only the adapter subclass runnable here
del _Dev2Suite
del RuntimeApiTests
