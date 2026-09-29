"""
Application-facing lifecycle of a PoS node: persisted identity, a background
event loop hosting the P2P Peer, and the room transition that
RoomSessionCoordinator triggers.

Nothing here has a default port, peer, room, identity, stake or reward: every
value is supplied by the caller (configuration, signalling response or user
input) and a missing one is an error.
"""
import asyncio
import concurrent.futures
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from agentguard.identity import EcdsaSigner
from agentguard.room_session import RoomSessionError
from consensus.pos.manifest import ManifestError, verify_manifest
from consensus.pos.node_service import PosNodeService, fingerprint
from consensus.pos.p2p import Peer, normalize_endpoint
from storage.node_storage import LegacyStorageError, NodeStorage, StorageConfigError, STORAGE_FORMAT_VERSION, _component

IDENTITY_DIR = ".identity"      # not a valid room id, so it can never collide with a room directory


def load_or_create_signer(data_root: str, node_id: str) -> EcdsaSigner:
    """
        The node's persisted signing identity. The room is not known yet at
        boot (the signer is needed to create/join one), so the identity lives
        beside - not inside - the per-room directories and is copied into
        <data-root>/<room-id>/<node-id>/ when a room is joined.
    """
    if not data_root or not node_id:
        raise StorageConfigError("data_root and node_id are required")
    directory = os.path.join(os.path.abspath(data_root), IDENTITY_DIR, _component("node_id", node_id))
    path = os.path.join(directory, "signer.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        if doc.get("format_version") != STORAGE_FORMAT_VERSION:
            raise LegacyStorageError(f"{path} was written under an older signing domain; use a clean data root")
        return EcdsaSigner.from_pem(doc["data"]["private_key_pem"])
    os.makedirs(directory, exist_ok=True)
    signer = EcdsaSigner.generate()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"format_version": STORAGE_FORMAT_VERSION,
                   "data": {"private_key_pem": signer.private_key.to_pem().decode("ascii")}}, fh)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return signer


class PosNodeRuntime:
    def __init__(self, *, data_root: str, node_id: str, node_name: str, bind_host: str, bind_port: int,
                 signer: EcdsaSigner, max_event_bytes: int, connect_timeout_s: float, transition_timeout_s: float,
                 stake_amount: Optional[int] = None, authority=None,
                 clock_ms: Optional[Callable[[], int]] = None):
        for name, value in (("data_root", data_root), ("node_id", node_id), ("node_name", node_name),
                            ("bind_host", bind_host), ("bind_port", bind_port), ("signer", signer),
                            ("max_event_bytes", max_event_bytes), ("connect_timeout_s", connect_timeout_s),
                            ("transition_timeout_s", transition_timeout_s)):
            if value in (None, "", 0):
                raise ValueError(f"{name} is required")
        self.data_root, self.node_id, self.node_name = data_root, node_id, node_name
        self.bind_host, self.bind_port = bind_host, bind_port
        self.signer = signer
        self.max_event_bytes = max_event_bytes
        self.connect_timeout_s, self.transition_timeout_s = connect_timeout_s, transition_timeout_s
        self.stake_amount = stake_amount
        self.authority = authority
        self.peer: Optional[Peer] = None
        self.members: List[dict] = []
        self.transition_report: Dict[str, Any] = {}
        self._peer_task: Optional[asyncio.Task] = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="pos-node", daemon=True)
        self._lock: Optional[asyncio.Lock] = None
        kwargs = {"clock_ms": clock_ms} if clock_ms else {}
        self.service = PosNodeService(lambda: self.peer, members_provider=lambda: list(self.members), **kwargs)
        self._thread.start()

    # ---- loop plumbing ---------------------------------------------------

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def call(self, coroutine, timeout: float):
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise RoomSessionError("timed out waiting for the node to finish the room transition") from None

    def stop(self):
        if self._loop.is_running():
            try:
                self.call(self._leave_room(), self.transition_timeout_s)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            if not self._thread.is_alive() and not self._loop.is_closed():
                self._loop.close()

    # ---- RoomSessionCoordinator callback ---------------------------------

    def on_verified_room(self, manifest: dict, members: List[dict]) -> None:
        """
            Blocks until the transition is complete: manifest and genesis
            verified, old-room peers disconnected, same-room peers connected
            (or their failure recorded). Raises RoomSessionError otherwise, so
            the caller never reports a room as operational half-way.
        """
        self.call(self._transition(manifest, members), self.transition_timeout_s)

    async def _transition(self, manifest: dict, members: List[dict]):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            try:
                verify_manifest(manifest)
            except ManifestError as exc:
                raise RoomSessionError(f"room manifest rejected: {exc}") from exc
            if self.peer is not None and self.peer.room_id == manifest["room_id"]:
                if self.peer.manifest != manifest:
                    raise RoomSessionError("room manifest differs from the one already applied to this node")
            else:
                await self._leave_room()
                await self._join_room(manifest)
            self.members = [dict(m) for m in members]
            self.transition_report = await self._connect_members(members)

    async def _leave_room(self):
        peer, task = self.peer, self._peer_task
        self.peer, self._peer_task = None, None
        if peer is None:
            return
        await peer.disconnect_all()
        peer.stop()
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                task.cancel()
        self.members = []

    async def _join_room(self, manifest: dict):
        try:
            storage = NodeStorage(self.data_root, manifest["room_id"], self.node_id)
            own_pem = self.signer.private_key.to_pem().decode("ascii")
            stored = storage.load_key()
            if stored is None:
                storage.save_key(own_pem)
            elif EcdsaSigner.from_pem(stored).public_key_pem != self.signer.public_key_pem:
                raise RoomSessionError("the key persisted for this room differs from the runtime signer")
            params = manifest["consensus"]["parameters"]
            if self.stake_amount is not None:
                allocations = {a["public_key"]: a["stake"] for a in manifest["genesis"]["allocations"]}
                if allocations.get(self.signer.public_key_pem) != self.stake_amount:
                    raise RoomSessionError("configured stake_amount differs from the signed genesis reservation")
            peer = Peer(self.bind_host, self.bind_port, self.node_name, True, "y", "y", manifest=manifest, storage=storage,
                        event_rules={"max_clock_skew_ms": params["max_clock_skew_ms"],
                                     "max_event_bytes": self.max_event_bytes, "authority": self.authority})
        except RoomSessionError:
            raise
        except (StorageConfigError, LegacyStorageError, ValueError, ManifestError) as exc:
            raise RoomSessionError(f"cannot open storage for the room: {exc}") from exc
        self.service.attach(peer)
        task = asyncio.create_task(peer.start(interactive=False, auto_stake=self.stake_amount))
        deadline = time.monotonic() + self.connect_timeout_s
        while not peer.ready.is_set():
            if task.done():
                raise RoomSessionError(f"node failed to start: {task.exception()}")
            if time.monotonic() > deadline:
                task.cancel()
                raise RoomSessionError("node did not become ready in time")
            await asyncio.sleep(0.02)
        self.peer, self._peer_task = peer, task
        peer.save_chain_to_disk()

    async def _connect_members(self, members: List[dict]) -> Dict[str, Any]:
        peer = self.peer
        own_fp = fingerprint(self.signer.public_key_pem)
        report: Dict[str, Any] = {"room_id": peer.room_id, "connected": [], "failed": []}
        pending: Dict[str, tuple] = {}
        for member in members:
            if member["public_key_fingerprint"] == own_fp or member["node_id"] == self.node_id:
                continue
            if any(fingerprint(public_key) == member["public_key_fingerprint"]
                   for ws, public_key in peer.ws_public_keys.items() if ws in peer.admitted):
                report["connected"].append(member["node_id"])
                continue
            try:
                endpoint = normalize_endpoint((member["advertised_host"], member["advertised_port"]))
            except Exception as exc:
                report["failed"].append({"node_id": member["node_id"], "reason": f"BAD_ENDPOINT: {exc}"})
                continue
            if endpoint == normalize_endpoint((self.bind_host, self.bind_port)):
                continue
            pending[member["node_id"]] = (member, endpoint)
            asyncio.create_task(peer.connect_to_peer(*endpoint))

        deadline = time.monotonic() + self.connect_timeout_s
        while pending and time.monotonic() < deadline:
            for node_id, (member, endpoint) in list(pending.items()):
                ws = next((w for w in peer.client_connections
                           if w.remote_address and tuple(w.remote_address[:2]) == endpoint and w in peer.admitted), None)
                if ws is None:
                    continue
                if fingerprint(peer.ws_public_keys[ws]) != member["public_key_fingerprint"]:
                    await ws.close()
                    report["failed"].append({"node_id": node_id, "reason": "FINGERPRINT_MISMATCH"})
                else:
                    report["connected"].append(node_id)
                del pending[node_id]
            if pending:
                await asyncio.sleep(0.05)
        for node_id in pending:
            report["failed"].append({"node_id": node_id, "reason": "UNREACHABLE_OR_OTHER_ROOM"})
        return report
