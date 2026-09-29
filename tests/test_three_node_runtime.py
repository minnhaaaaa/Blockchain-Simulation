"""
Three PoS nodes as an application would run them: persisted identities,
signalling-driven room creation/joining, dynamic ports, temporary directories,
automatic staking. No sockets or paths are fixed in the test.
"""
import socket
import time
import uuid
from pathlib import Path

import pytest

from agentguard.node_service import SubmissionRejected
from agentguard.room_session import RoomSessionCoordinator, RoomSessionError
from agentguard.schema_validation import SchemaValidator
from consensus.pos import events as ev
from consensus.pos.blockchain_structures import Wallet
from consensus.pos.node_service import fingerprint
from consensus.pos.runtime import PosNodeRuntime, load_or_create_signer
from signalling.registry import RoomRegistry
from tests.factory import JobScript
from tests.fakes import RegistryClient
from tests.test_runtime_api import ROOT

PARAMS = {"epoch_ms": 600, "max_clock_skew_ms": 60_000, "finality_depth": 1, "max_connections": 8,
          "block_reward": 0, "minimum_stake": 1}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def until(predicate, timeout=15.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


class NodeUnderTest:
    def __init__(self, root: Path, registry, schemas, index: int, stake_amount=None):
        self.node_id = str(uuid.uuid4())
        self.port = free_port()
        data_root = str(root / f"data-{index}")
        self.signer = load_or_create_signer(data_root, self.node_id)
        self.runtime = PosNodeRuntime(
            data_root=data_root, node_id=self.node_id, node_name=f"node-{index}", bind_host="127.0.0.1",
            bind_port=self.port, signer=self.signer, max_event_bytes=200_000, connect_timeout_s=5,
            transition_timeout_s=30, stake_amount=stake_amount)
        self.session = RoomSessionCoordinator(
            RegistryClient(registry), schemas, self.signer, self.node_id, f"node-{index}", "127.0.0.1", self.port,
            on_verified_room=self.runtime.on_verified_room)
        self.service = self.runtime.service
        self.data_root = data_root

    @property
    def peer(self):
        return self.runtime.peer


@pytest.fixture
def network(tmp_path):
    schemas = SchemaValidator(ROOT / "contracts" / "schemas")
    registry = RoomRegistry(tmp_path / "rooms.sqlite3", 60_000, schemas)
    nodes = [NodeUnderTest(tmp_path, registry, schemas, i, stake_amount=50 if i == 0 else None) for i in range(3)]
    yield nodes, registry, schemas, tmp_path
    for n in nodes:
        n.runtime.stop()


def create_room(nodes, room_id="room-three-nodes"):
    creator = nodes[0]
    creator.session.configure({
        "operation": "create", "room_id": room_id, "protocol_version": "1", "consensus_parameters": PARAMS,
        "genesis_allocations": [{"public_key": n.signer.public_key_pem, "amount": 1000} for n in nodes]})
    for n in nodes[1:]:
        n.session.configure({"operation": "join", "room_id": room_id})
    return room_id


def test_three_nodes_join_converge_and_finalize(network):
    nodes, *_ = network
    room_id = create_room(nodes)
    a, b, c = nodes

    # every node applied the same signed manifest and derived the same genesis
    assert len({n.peer.chain.chain[0].hash for n in nodes}) == 1
    assert all(n.peer.room_id == room_id for n in nodes)
    # storage lives at <data-root>/<room-id>/<node-id>/
    for n in nodes:
        assert (Path(n.data_root) / room_id / n.node_id / "keys.json").exists()
        assert (Path(n.data_root) / room_id / n.node_id / "manifest.json").exists()
    # joiners connected to the discovered peers, and only after the transition finished
    assert c.runtime.transition_report["failed"] == [] and len(c.runtime.transition_report["connected"]) == 2
    assert until(lambda: len(a.peer.admitted) == 2)

    job = JobScript(room_id, a.signer_wallet if hasattr(a, "signer_wallet") else Wallet(), Wallet())
    # use the node's own signer as job owner so the event is genuinely signed by the persisted identity
    owner = Wallet(a.signer.private_key.to_pem().decode())
    worker = Wallet(b.signer.private_key.to_pem().decode())
    job = JobScript(room_id, owner, worker)
    created = a.service.submit_event(job.created())
    assert created.ledger_state == "submitted"
    assert until(lambda: all(n.service.get_event(created.event_id) for n in nodes))       # gossip

    # a's auto-staker produces the block; all nodes converge on it
    assert until(lambda: all(n.service.get_event_state(created.event_id) in ("included", "finalized") for n in nodes))
    assert len({n.peer.chain.lastBlock.hash for n in nodes}) == 1

    # more work produces more blocks; the first event becomes finalized everywhere
    accepted = b.service.submit_event(job.accepted())
    assert until(lambda: all(n.service.get_event_state(accepted.event_id) in ("included", "finalized") for n in nodes))
    assert until(lambda: all(n.service.get_event_state(created.event_id) == "finalized" for n in nodes))
    summary = c.service.get_chain_summary(10)
    assert summary["height"] >= 2 and summary["finalized_height"] >= 1
    assert len({n.peer.chain.lastBlock.hash for n in nodes}) == 1
    peers = c.service.get_peer_summaries()
    assert len(peers) == 2 and {p["connection_state"] for p in peers} == {"connected"}


def test_invalid_forged_replayed_duplicate_events_never_accepted_anywhere(network):
    nodes, *_ = network
    room_id = create_room(nodes)
    a, b, c = nodes
    owner = Wallet(a.signer.private_key.to_pem().decode())
    worker = Wallet(b.signer.private_key.to_pem().decode())
    job = JobScript(room_id, owner, worker)
    good = job.created()
    a.service.submit_event(good)
    assert until(lambda: all(n.service.get_event_state(good["event_id"]) in ("included", "finalized") for n in nodes))

    forged_signature = ev.sign_event({k: v for k, v in job.accepted().items() if k not in ("event_hash", "signature")}, Wallet().private_key)
    tampered = job.accepted(); tampered["payload"]["accepted_at_ms"] += 1
    replay_new_id = ev.sign_event({**{k: v for k, v in good.items() if k not in ("event_hash", "signature", "event_id")},
                                   "event_id": str(uuid.uuid4())}, owner.private_key)
    reuse = ev.sign_event({**{k: v for k, v in good.items() if k not in ("event_hash", "signature")},
                           "created_at_ms": good["created_at_ms"] + 1}, owner.private_key)
    for svc in (a.service, b.service, c.service):
        for bad in (forged_signature, tampered, replay_new_id, reuse):
            with pytest.raises(SubmissionRejected):
                svc.submit_event(bad)
        again = svc.submit_event(good)                # exact duplicate: idempotent, no second copy
        assert again.event_id == good["event_id"]
    time.sleep(1.5)
    for n in nodes:
        included = [e["event_id"] for blk in n.peer.chain.chain for e in blk.events]
        assert included == [good["event_id"]]
        assert n.peer.event_pool == []
        assert set(n.peer.ledger.events_by_id) == {good["event_id"]}


def test_room_transition_disconnects_old_room_peers_and_reports_after_completion(network):
    nodes, registry, schemas, tmp_path = network
    room_id = create_room(nodes)
    a, b, c = nodes
    assert until(lambda: len(b.peer.admitted) == 2)

    # b moves to a different room created by nobody else: old-room peers must be dropped
    old_peer = b.peer
    b.session.configure({"operation": "create", "room_id": "another-room-x", "protocol_version": "1",
                         "consensus_parameters": PARAMS,
                         "genesis_allocations": [{"public_key": b.signer.public_key_pem, "amount": 10}]})
    assert b.peer is not old_peer and b.peer.room_id == "another-room-x"
    assert old_peer.server_connections == set() and old_peer.client_connections == set()
    assert until(lambda: len(a.peer.admitted) == 1)                 # only c remains connected to a
    assert b.peer.chain.chain[0].hash != a.peer.chain.chain[0].hash
    assert b.service.get_event(str(uuid.uuid4())) is None
    # b's storage for the new room is namespaced separately and holds the same persisted identity
    assert (Path(b.data_root) / "another-room-x" / b.node_id / "keys.json").exists()
    assert (Path(b.data_root) / room_id / b.node_id / "keys.json").exists()

    # an old-room node cannot re-attach: the handshake carries the room and genesis
    import asyncio
    async def attempt():
        await old_peer.connect_to_peer("127.0.0.1", b.port)
    fut = asyncio.run_coroutine_threadsafe(attempt(), a.runtime._loop)
    time.sleep(1.0)
    assert len(b.peer.admitted) == 0


def test_manifest_and_fingerprint_verification_on_transition(network):
    nodes, registry, schemas, tmp_path = network
    room_id = create_room(nodes)
    a, b, c = nodes
    manifest = a.peer.manifest

    forged = {**manifest, "genesis": {**manifest["genesis"], "allocations": [
        {"public_key": a.signer.public_key_pem, "amount": 999_999}]}}
    with pytest.raises(RoomSessionError):
        c.runtime.on_verified_room(forged, [])
    with pytest.raises(RoomSessionError):        # same room id, different (validly signed) manifest is refused
        other = Wallet()
        from tests.factory import make_manifest
        c.runtime.on_verified_room(make_manifest(other, room_id=room_id), [])
    assert c.peer.manifest == manifest             # failed transitions leave the node in its verified room

    members = [{"schema_version": 1, "room_id": room_id, "node_id": str(uuid.uuid4()), "name": "impostor",
                "advertised_host": "127.0.0.1", "advertised_port": b.port,
                "public_key_fingerprint": fingerprint(Wallet().public_key_pem),
                "joined_at_ms": 1, "last_heartbeat_ms": 1}]
    c.runtime.on_verified_room(manifest, members)
    assert c.runtime.transition_report["failed"] == [{"node_id": members[0]["node_id"], "reason": "FINGERPRINT_MISMATCH"}]
    assert c.runtime.transition_report["connected"] == []


def test_persisted_identity_and_chain_survive_restart(network):
    nodes, registry, schemas, tmp_path = network
    room_id = create_room(nodes)
    a, b, c = nodes
    owner = Wallet(a.signer.private_key.to_pem().decode())
    job = JobScript(room_id, owner, Wallet())
    created = a.service.submit_event(job.created())
    assert until(lambda: b.service.get_event_state(created.event_id) in ("included", "finalized"))
    head = b.peer.chain.lastBlock.hash
    b.runtime.stop()

    restarted = NodeUnderTest.__new__(NodeUnderTest)
    restarted.node_id, restarted.port, restarted.data_root = b.node_id, free_port(), b.data_root
    restarted.signer = load_or_create_signer(b.data_root, b.node_id)
    assert restarted.signer.public_key_pem == b.signer.public_key_pem            # same persisted identity
    restarted.runtime = PosNodeRuntime(
        data_root=b.data_root, node_id=b.node_id, node_name="node-1", bind_host="127.0.0.1", bind_port=restarted.port,
        signer=restarted.signer, max_event_bytes=200_000, connect_timeout_s=5, transition_timeout_s=30)
    try:
        restarted.runtime.on_verified_room(a.peer.manifest, [])
        assert restarted.runtime.peer.chain.lastBlock.hash == head                # chain reloaded and re-validated
        assert restarted.runtime.service.get_event(created.event_id)["event_id"] == created.event_id
    finally:
        restarted.runtime.stop()
