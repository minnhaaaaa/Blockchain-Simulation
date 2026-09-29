"""
Test factory for Developer 2 and the test-suite: builds rooms, in-process
nodes with a working NodeService, and correctly signed agent events.

Every identity, ID and timestamp is generated at call time. Nothing here is
imported by production code.
"""
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from consensus.pos import events as ev
from consensus.pos.blockchain_structures import Wallet
from consensus.pos.manifest import sign_manifest
from consensus.pos.node_service import PosNodeService
from consensus.pos.p2p import Peer
from storage.node_storage import NodeStorage


class FakeClock:
    def __init__(self, start_ms: Optional[int] = None):
        self.ms = start_ms if start_ms is not None else int(time.time() * 1000)

    def __call__(self) -> int:
        return self.ms

    def advance(self, ms: int = 1):
        self.ms += ms
        return self.ms


def new_id() -> str:
    return str(uuid.uuid4())


def make_manifest(creator: Wallet, *, room_id: Optional[str] = None, allocations=None, epoch_ms=100,
                  max_clock_skew_ms=5_000, finality_depth=2, max_connections=8, block_reward=6,
                  minimum_stake=1, created_at_ms=None, stake_amount=5) -> Dict[str, Any]:
    created = created_at_ms if created_at_ms is not None else int(time.time() * 1000) - 3_600_000
    allocations = allocations or [{"public_key": creator.public_key_pem, "amount": 1_000}]
    allocations = [{**a, "stake": a.get("stake", stake_amount if a["public_key"] == creator.public_key_pem else 0)} for a in allocations]
    return sign_manifest({
        "schema_version": 1,
        "room_id": room_id or ("room-" + uuid.uuid4().hex[:12]),
        "protocol_version": "1",
        "consensus": {"type": "pos", "parameters": {
            "epoch_ms": epoch_ms, "max_clock_skew_ms": max_clock_skew_ms, "finality_depth": finality_depth,
            "max_connections": max_connections, "block_reward": block_reward, "minimum_stake": minimum_stake}},
        "genesis": {"block_id": new_id(), "created_at_ms": created, "allocations": allocations},
        "creator_public_key": creator.public_key_pem,
        "created_at_ms": created,
    }, creator.private_key)


def make_node(manifest, wallet: Wallet, data_root: str, *, clock=None, authority=None, name="node",
              port=0, max_event_bytes=64_000):
    """A staker Peer (network not started) plus its NodeService. Returns (peer, service)."""
    storage = NodeStorage(data_root, manifest["room_id"], str(uuid.uuid4()))
    storage.save_key(wallet.private_key_pem)
    peer = Peer("127.0.0.1", port, name, True, "y", "n", manifest=manifest, storage=storage,
                event_rules={"max_clock_skew_ms": manifest["consensus"]["parameters"]["max_clock_skew_ms"],
                             "max_event_bytes": max_event_bytes, "authority": authority})
    assert peer.wallet.public_key_pem == wallet.public_key_pem
    from consensus.pos import manifest as room_manifest
    from consensus.pos.blockchain_structures import Chain
    peer.chain = Chain(genesis_block=room_manifest.build_genesis(manifest))
    peer.chain.params = peer.params
    peer.rebuild_ledger()
    service = PosNodeService(lambda: peer, clock_ms=clock) if clock else PosNodeService(lambda: peer)
    service.attach(peer)
    return peer, service


def make_solo_room(data_root: str, **kwargs):
    creator = Wallet()
    clock = kwargs.pop("clock", None) or FakeClock()
    manifest = make_manifest(creator, **kwargs)
    peer, service = make_node(manifest, creator, data_root, clock=clock)
    return {"manifest": manifest, "creator": creator, "peer": peer, "service": service, "clock": clock}


# ---- event builders --------------------------------------------------------

def _envelope(room_id, job_id, actor: Wallet, etype, payload, sequence, previous_hash, created_at_ms):
    return ev.sign_event({
        "schema_version": 1, "event_id": new_id(), "event_type": etype, "room_id": room_id, "job_id": job_id,
        "actor_public_key": actor.public_key_pem, "sequence": sequence, "created_at_ms": created_at_ms,
        "previous_event_hash": previous_hash, "payload": payload,
    }, actor.private_key)


def make_policy(job_id, owner: Wallet, now_ms, tool_id="text.summarise", effect="allow"):
    return {
        "schema_version": 1, "policy_id": new_id(), "job_id": job_id, "owner_public_key": owner.public_key_pem,
        "rules": [{"rule_id": new_id(), "tool_id": tool_id, "effect": effect, "read_artifact_ids": [],
                   "write_scopes": [], "argument_constraints": {}}],
        "limits": {"max_actions": 10, "max_runtime_ms_per_action": 1_000, "max_output_bytes_per_action": 1_000},
        "created_at_ms": now_ms,
    }


class JobScript:
    """Builds a correctly chained sequence of signed events for one job."""

    def __init__(self, room_id: str, owner: Wallet, worker: Wallet, gateway: Optional[Wallet] = None, clock=None,
                 tool_id="text.summarise"):
        self.room_id, self.owner, self.worker = room_id, owner, worker
        self.gateway = gateway or worker
        self.clock = clock or FakeClock()
        self.job_id = new_id()
        self.tool_id = tool_id
        self.sequence = 0
        self.previous_hash: Optional[str] = None
        self.policy = make_policy(self.job_id, owner, self.clock(), tool_id)
        self.actions: Dict[str, Dict[str, Any]] = {}
        self.action_count = 0

    def probe(self):
        """Context manager: events built inside do not advance this script (for invalid/hypothetical events)."""
        from contextlib import contextmanager

        @contextmanager
        def _probe():
            saved = (self.sequence, self.previous_hash, self.clock.ms, self.action_count, dict(self.actions))
            try:
                yield self
            finally:
                self.sequence, self.previous_hash, self.clock.ms, self.action_count, self.actions = saved[0], saved[1], saved[2], saved[3], saved[4]

        return _probe()

    def _emit(self, actor, etype, payload, *, advance=True):
        event = _envelope(self.room_id, self.job_id, actor, etype, payload, self.sequence, self.previous_hash, self.clock())
        if advance:
            self.sequence += 1
            self.previous_hash = event["event_hash"]
            self.clock.advance(1)
        return event

    def created(self):
        job = {"schema_version": 1, "job_id": self.job_id, "room_id": self.room_id,
               "owner_public_key": self.owner.public_key_pem, "title": "t", "instructions": "do it",
               "provider_id": "provider", "input_artifacts": [], "policy": self.policy, "created_at_ms": self.clock()}
        return self._emit(self.owner, "job.created", job)

    def accepted(self):
        return self._emit(self.worker, "job.accepted", {
            "schema_version": 1, "job_id": self.job_id, "worker_public_key": self.worker.public_key_pem,
            "accepted_at_ms": self.clock()})

    def proposed(self):
        action_id = new_id()
        payload = {"schema_version": 1, "action_id": action_id, "job_id": self.job_id,
                   "action_sequence": self.action_count, "tool_id": self.tool_id, "arguments": {},
                   "input_artifact_ids": [], "expected_output_kind": "text",
                   "proposer_public_key": self.worker.public_key_pem, "proposed_at_ms": self.clock()}
        self.actions[action_id] = payload
        self.action_count += 1
        return self._emit(self.worker, "action.proposed", payload), action_id

    def decision(self, action_id, etype, *, decision, basis, actor=None):
        actor = actor or (self.owner if basis == "human" else self.gateway)
        return self._emit(actor, etype, {
            "schema_version": 1, "decision_id": new_id(), "job_id": self.job_id, "action_id": action_id,
            "decision": decision, "basis": basis, "decided_by_public_key": actor.public_key_pem,
            "reason_code": "OK", "reason": "test", "policy_hash": ev.policy_hash(self.policy),
            "decided_at_ms": self.clock()})

    def allowed(self, action_id):
        return self.decision(action_id, "action.allowed", decision="allow", basis="policy")

    def completed(self, action_id, *, status="success", receipt_id=None):
        proposal = self.actions[action_id]
        import hashlib
        from canonical import canonical_json
        receipt = ev.sign_receipt({
            "schema_version": 1, "receipt_id": receipt_id or new_id(), "job_id": self.job_id, "action_id": action_id,
            "worker_public_key": self.worker.public_key_pem, "tool_id": proposal["tool_id"], "tool_version": "1",
            "request_hash": hashlib.sha256(canonical_json(proposal)).hexdigest(), "output_hash": "0" * 64,
            "output_artifacts": [], "status": status,
            "started_at_ms": self.clock(), "completed_at_ms": self.clock()}, self.worker.private_key)
        return self._emit(self.worker, "action.completed", receipt)

    def finished(self, status="completed"):
        return self._emit(self.worker, "job.completed" if status == "completed" else "job.failed", {
            "schema_version": 1, "job_id": self.job_id, "status": status, "output_artifacts": [],
            "summary": "done", "completed_at_ms": self.clock()})

    def violation(self, actor=None, action_id=None):
        payload = {"schema_version": 1, "violation_id": new_id(), "job_id": self.job_id, "category": "replay",
                   "reason_code": "REPLAY", "message": "m", "evidence_hash": "0" * 64,
                   "detected_at_ms": self.clock()}
        if action_id:
            payload["action_id"] = action_id
        return self._emit(actor or self.gateway, "security.violation", payload)
