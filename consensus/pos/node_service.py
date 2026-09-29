"""
Adapter between Developer 2's runtime (agentguard.node_service.NodeService)
and the PoS node. Every value returned is a JSON-serialisable copy; nothing
here hands out a reference into chain, ledger or pool internals.

`peer_provider` returns the Peer for the room currently joined (or None before
the first room), so the service keeps working across room transitions.
"""
import hashlib
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from agentguard.node_service import NodeUnavailable, Submission, SubmissionRejected
from consensus.pos.events import EventRejection

ZERO_HASH = "0" * 64


def fingerprint(public_key_pem: str) -> str:
    return hashlib.sha256(public_key_pem.encode("utf-8")).hexdigest()


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _now_ms() -> int:
    return int(time.time() * 1000)


class PosNodeService:
    def __init__(self, peer_provider: Callable[[], Any], clock_ms: Callable[[], int] = _now_ms,
                 members_provider: Callable[[], List[dict]] = lambda: []):
        self._peer_provider = peer_provider
        self._clock_ms = clock_ms
        self._members_provider = members_provider
        self._submissions: Dict[str, Submission] = {}
        self._listeners: List[Callable[[dict], None]] = []

    # ---- helpers ---------------------------------------------------------

    def _require_peer(self):
        peer = self._peer_provider()
        if peer is None or peer.chain is None or not peer.event_rules:
            raise NodeUnavailable("this node has not joined a room yet")
        return peer

    def _height_of(self, peer, event_id: str) -> Optional[int]:
        for height, block in enumerate(peer.chain.chain):
            for event in block.events:
                if event["event_id"] == event_id:
                    return height
        return None

    @staticmethod
    def _state(peer, height: Optional[int]) -> str:
        if height is None:
            return "submitted"
        head = len(peer.chain.chain) - 1
        return "finalized" if head - height >= peer.params.finality_depth else "included"

    # ---- NodeService -----------------------------------------------------

    def submit_event(self, event: dict) -> Submission:
        """
            Validate fully before anything is queued. A refused event raises
            SubmissionRejected (with `.code`) and is never present in
            accepted state. Repeating an accepted identical event returns its
            existing submission; reusing an ID with other bytes is ID_REUSE.
        """
        peer = self._require_peer()
        event_id = event.get("event_id") if isinstance(event, dict) else None
        with peer.state_lock:
            existing = self._locate(peer, event_id) if isinstance(event_id, str) else None
            if existing is not None and existing[0] == event:
                return self._submission(existing[0], self._state(peer, existing[1]))
            try:
                peer.accept_event(event, self._clock_ms())
            except EventRejection as rejection:
                exc = SubmissionRejected(f"{rejection.code}: {rejection.message}")
                exc.code, exc.reason = rejection.code, rejection.message
                raise exc from None
        peer.schedule_event_gossip(event)
        return self._submission(event, "submitted")

    def _locate(self, peer, event_id):
        """(event, height|None) from the chain or the pending pool."""
        height = self._height_of(peer, event_id)
        if height is not None:
            for event in peer.chain.chain[height].events:
                if event["event_id"] == event_id:
                    return event, height
        for event in peer.event_pool:
            if event["event_id"] == event_id:
                return event, None
        return None

    def _submission(self, event, state) -> Submission:
        known = self._submissions.get(event["event_id"])
        submission_id = known.submission_id if known else str(uuid.uuid4())
        result = Submission(submission_id, event["event_id"], state, event["event_hash"])
        self._submissions[event["event_id"]] = result
        return result

    def get_event(self, event_id: str) -> Optional[dict]:
        peer = self._peer_provider()
        if peer is None or peer.chain is None or not isinstance(event_id, str):
            return None
        with peer.state_lock:
            hit = self._locate(peer, event_id)
            return _copy(hit[0]) if hit else None

    def get_event_state(self, event_id: str) -> Optional[str]:
        """submitted | included | finalized, or None when the ledger has never accepted the event."""
        peer = self._peer_provider()
        if peer is None or peer.chain is None:
            return None
        with peer.state_lock:
            hit = self._locate(peer, event_id)
            return self._state(peer, hit[1]) if hit else None

    def list_job_events(self, job_id: str) -> List[dict]:
        peer = self._peer_provider()
        if peer is None or peer.chain is None:
            return []
        with peer.state_lock:
            events = [e for b in peer.chain.chain for e in b.events if e["job_id"] == job_id]
            events += [e for e in peer.event_pool if e["job_id"] == job_id]
            return _copy(sorted(events, key=lambda e: e["sequence"]))

    def _block_summary(self, peer, height: int, finalized: int) -> dict:
        block = peer.chain.chain[height]
        return {
            "height": height,
            "block_id": block.id,
            "hash": block.hash,
            "previous_hash": block.prevHash or ZERO_HASH,
            "creator_fingerprint": fingerprint(block.creator),
            "created_at_ms": int(block.ts),
            "transaction_count": len(block.transactions) + len(block.events),
            "finality": "finalized" if height <= finalized else "confirmed",
        }

    def get_chain_summary(self, limit: int) -> dict:
        peer = self._peer_provider()
        if peer is None or peer.chain is None:
            return {"height": 0, "finalized_height": 0, "head_hash": ZERO_HASH, "blocks": []}
        with peer.state_lock:
            chain = peer.chain.chain
            height = len(chain) - 1
            finalized = max(0, height - peer.params.finality_depth)
            start = max(0, len(chain) - max(0, limit))
            return {
                "height": height,
                "finalized_height": finalized,
                "head_hash": chain[-1].hash,
                "blocks": [self._block_summary(peer, h, finalized) for h in range(start, len(chain))],
            }

    def get_block(self, block_id: str) -> Optional[dict]:
        peer = self._peer_provider()
        if peer is None or peer.chain is None:
            return None
        with peer.state_lock:
            finalized = max(0, len(peer.chain.chain) - 1 - peer.params.finality_depth)
            for height, block in enumerate(peer.chain.chain):
                if block.id == block_id or block.hash == block_id:
                    return {"block": self._block_summary(peer, height, finalized), "events": _copy(block.events)}
        return None

    def get_peer_summaries(self) -> List[dict]:
        peer = self._peer_provider()
        if peer is None:
            return []
        members = {m["public_key_fingerprint"]: m for m in self._members_provider()}
        now = self._clock_ms()
        items = []
        with peer.state_lock:
            connected_keys = {peer.ws_public_keys[ws] for ws in (peer.server_connections | peer.client_connections)
                              if ws in peer.ws_public_keys and ws in peer.admitted}
            seen = set()
            for (host, port), (name, public_key) in sorted(peer.known_peers.items()):
                fp = fingerprint(public_key)
                member = members.get(fp)
                seen.add(fp)
                items.append({
                    "node_id": member["node_id"] if member else str(uuid.uuid5(uuid.NAMESPACE_URL, fp)),
                    "name": name, "advertised_host": host, "advertised_port": port,
                    "public_key_fingerprint": fp, "discovery_state": "discovered",
                    "connection_state": "connected" if public_key in connected_keys else "disconnected",
                    "last_seen_ms": member["last_heartbeat_ms"] if member else now,
                })
            for fp, member in members.items():
                if fp in seen or fp == fingerprint(peer.wallet.public_key_pem):
                    continue
                items.append({
                    "node_id": member["node_id"], "name": member["name"],
                    "advertised_host": member["advertised_host"], "advertised_port": member["advertised_port"],
                    "public_key_fingerprint": fp, "discovery_state": "discovered",
                    "connection_state": "disconnected", "last_seen_ms": member["last_heartbeat_ms"],
                })
        return items

    def get_stake_snapshot(self) -> dict:
        peer = self._peer_provider()
        if peer is None or peer.chain is None:
            return {"epoch_seed": ZERO_HASH, "total_stake": 0, "latest_proposer_fingerprint": None, "items": []}
        with peer.state_lock:
            stakers = dict(peer.current_stakers)
            last = peer.chain.lastBlock
            return {
                "epoch_seed": peer.chain.epoch_seed(),
                "total_stake": sum(stakers.values()),
                "latest_proposer_fingerprint": fingerprint(last.creator) if last.creator and len(peer.chain.chain) > 1 else None,
                "items": [{"staker_fingerprint": fingerprint(k), "amount": v} for k, v in sorted(stakers.items())],
            }

    def subscribe_state_changes(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        """
            Callbacks live on the service, not on a Peer, so they survive room
            transitions. Each change carries `event_id` and `ledger_state`
            (submitted | included | finalized | rejected).
        """
        self._listeners.append(callback)

        def cancel():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return cancel

    def attach(self, peer):
        """Forward a Peer's state-change notifications to this service's subscribers."""
        peer.state_listeners.append(self._dispatch)

    def _dispatch(self, change: dict):
        for listener in list(self._listeners):
            try:
                listener(dict(change))
            except Exception as exc:  # a subscriber must never break consensus
                print(f"state-change subscriber failed: {exc}")

    def produce_block(self, stake_amount: Optional[int] = None):
        """Run this node's stake lottery once for the pending pool (single-process rooms and tests)."""
        peer = self._require_peer()
        with peer.state_lock:
            if stake_amount is not None:
                peer.register_stake(stake_amount)
            block = peer.try_produce_block()
        if block is None:
            return None
        return {"hash": block.hash, "height": len(peer.chain.chain) - 1, "event_ids": [e["event_id"] for e in block.events]}
