"""
Signed agent-event validation and the derived per-job ledger projection.

Receivers validate in the order fixed by docs/SCHEMAS.md section 11:
size bound -> JSON schema -> canonical hash -> signature -> identity /
authorization -> temporal checks -> duplicate / replay -> state transition.
A failure raises EventRejection with a stable reason code and never applies
partial state.

Signature encoding: ECDSA over secp256k1 with SHA-256, raw r||s bytes,
standard Base64. Signed bytes are `UTF8(domain + "\\n") || canonical_json(...)`.
"""
import base64
import copy
import hashlib
import json
import os
from typing import Any, Callable, Dict, List, Optional, Set

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from canonical import canonical_json, signing_bytes
from shared_blockchain_structures import verify_signature

DOMAIN_EVENT = "agentguard.agent-event.v1"
DOMAIN_RECEIPT = "agentguard.receipt.v1"
DOMAIN_ROOM_MANIFEST = "agentguard.room-manifest.v1"

SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "contracts", "schemas"
)
_SCHEMA_BASE = "https://agentguard.invalid/schemas/"

# Event name -> (required payload decision, required basis(es))
DECISION_EVENTS = {
    "action.allowed": ("allow", {"policy"}),
    "action.denied": ("deny", {"policy", "validator"}),
    "action.approval_required": ("approval_required", {"policy"}),
    "action.approved": ("approved", {"human"}),
    "action.rejected": ("rejected", {"human"}),
}

TERMINAL_ACTION_STATES = {"denied", "rejected", "succeeded", "failed"}
TERMINAL_JOB_STATES = {"completed", "failed"}


class EventRejection(Exception):
    """A submission was refused. `code` is a stable reason code."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message}


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

_registry: Optional[Registry] = None
_validators: Dict[str, Draft202012Validator] = {}


def _load_registry() -> Registry:
    global _registry
    if _registry is None:
        registry = Registry()
        for name in sorted(os.listdir(SCHEMA_DIR)):
            if not name.endswith(".schema.json"):
                continue
            with open(os.path.join(SCHEMA_DIR, name), "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            # The frozen files use urn: $ids, which cannot resolve their own
            # relative "./x.schema.json" references. Serve each one under a
            # resolvable base without touching the frozen files.
            doc["$id"] = _SCHEMA_BASE + name
            registry = registry.with_resource(doc["$id"], Resource.from_contents(doc))
        _registry = registry
    return _registry


def schema_validator(name: str) -> Draft202012Validator:
    """Validator for a frozen schema file, e.g. `agent-event`."""
    if name not in _validators:
        registry = _load_registry()
        schema = registry.get_or_retrieve(_SCHEMA_BASE + name + ".schema.json").value.contents
        _validators[name] = Draft202012Validator(schema, registry=registry)
    return _validators[name]


def schema_errors(name: str, instance: Any) -> List[str]:
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(schema_validator(name).iter_errors(instance), key=lambda e: list(map(str, e.absolute_path)))
    ]


# --------------------------------------------------------------------------
# Hashing / signing
# --------------------------------------------------------------------------

def _unsigned(event: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in event.items() if k not in ("event_hash", "signature")}


def event_signing_bytes(event: Dict[str, Any]) -> bytes:
    return signing_bytes(DOMAIN_EVENT, _unsigned(event))


def compute_event_hash(event: Dict[str, Any]) -> str:
    return hashlib.sha256(event_signing_bytes(event)).hexdigest()


def sign_event(unsigned_event: Dict[str, Any], private_key) -> Dict[str, Any]:
    """Return a copy with `event_hash` and `signature` filled in."""
    event = copy.deepcopy(_unsigned(unsigned_event))
    data = event_signing_bytes(event)
    event["event_hash"] = hashlib.sha256(data).hexdigest()
    event["signature"] = base64.b64encode(private_key.sign(data)).decode()
    return event


def receipt_signing_bytes(receipt: Dict[str, Any]) -> bytes:
    return signing_bytes(DOMAIN_RECEIPT, {k: v for k, v in receipt.items() if k != "signature"})


def sign_receipt(unsigned_receipt: Dict[str, Any], private_key) -> Dict[str, Any]:
    receipt = {k: v for k, v in unsigned_receipt.items() if k != "signature"}
    receipt["signature"] = base64.b64encode(private_key.sign(receipt_signing_bytes(receipt))).decode()
    return receipt


def manifest_signing_bytes(manifest: Dict[str, Any]) -> bytes:
    return signing_bytes(DOMAIN_ROOM_MANIFEST, {k: v for k, v in manifest.items() if k != "signature"})


def policy_hash(policy: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(policy)).hexdigest()


def _verify_b64(public_key_pem: str, signature_b64: str, data: bytes) -> bool:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception:
        return False
    return verify_signature(public_key_pem, signature, data)


# --------------------------------------------------------------------------
# Projection
# --------------------------------------------------------------------------

class JobState:
    def __init__(self, job_id: str, owner: str, policy_hash_value: str, expires_at_ms: Optional[int]):
        self.job_id = job_id
        self.owner = owner
        self.policy_hash = policy_hash_value
        self.expires_at_ms = expires_at_ms
        self.worker: Optional[str] = None
        self.status = "open"
        self.next_sequence = 0
        self.last_event_hash: Optional[str] = None
        self.last_created_at_ms = 0
        self.actions: Dict[str, str] = {}          # action_id -> state
        self.action_payloads: Dict[str, Dict[str, Any]] = {}
        self.next_action_sequence = 0

    @property
    def pending_approvals(self) -> int:
        return sum(1 for s in self.actions.values() if s == "pending")


class Authority:
    """
    Who may issue policy decisions and violations. `is_gateway` / `is_validator`
    are supplied by the runtime; by default a job's accepted worker acts as the
    gateway for its own job (the gateway runs beside the worker) and any room
    node may record a validator violation.
    """

    def __init__(
        self,
        is_gateway: Optional[Callable[[str, "JobState"], bool]] = None,
        is_validator: Optional[Callable[[str], bool]] = None,
    ):
        self._is_gateway = is_gateway
        self._is_validator = is_validator

    def gateway(self, key: str, job: JobState) -> bool:
        if self._is_gateway is not None:
            return bool(self._is_gateway(key, job))
        return key == job.worker

    def validator(self, key: str) -> bool:
        if self._is_validator is not None:
            return bool(self._is_validator(key))
        return True


class JobLedger:
    """
    Deterministic projection of accepted events. `check` validates without
    mutating; `apply` mutates and must only follow a successful `check`.
    """

    def __init__(
        self,
        room_id: str,
        max_clock_skew_ms: int,
        max_event_bytes: int,
        authority: Optional[Authority] = None,
    ):
        if not room_id:
            raise ValueError("room_id is required")
        self.room_id = room_id
        self.max_clock_skew_ms = max_clock_skew_ms
        self.max_event_bytes = max_event_bytes
        self.authority = authority or Authority()
        self.jobs: Dict[str, JobState] = {}
        self.events_by_id: Dict[str, str] = {}          # event_id -> event_hash
        self.event_order: List[str] = []
        self.namespaces: Dict[str, Set[str]] = {
            "action": set(), "decision": set(), "receipt": set(), "violation": set(),
        }

    def clone(self) -> "JobLedger":
        return copy.deepcopy(self)

    # ---- validation ------------------------------------------------------

    def check(self, event: Any, now_ms: Optional[int] = None) -> None:
        """
        Raise EventRejection unless `event` is acceptable next state.
        `now_ms` enables the wall-clock skew rule (mempool submission); block
        replay passes None so history can be re-validated at any later time.
        """
        # 1. size bound
        try:
            size = len(canonical_json(event))
        except Exception:
            raise EventRejection("VALIDATION_FAILED", "event is not canonicalisable JSON")
        if size > self.max_event_bytes:
            raise EventRejection("PAYLOAD_TOO_LARGE", f"event exceeds {self.max_event_bytes} bytes")
        if not isinstance(event, dict):
            raise EventRejection("VALIDATION_FAILED", "event must be an object")

        # 2. schema
        errors = schema_errors("agent-event", event)
        if errors:
            raise EventRejection("VALIDATION_FAILED", "; ".join(errors[:5]))

        # 3. canonical hash, 4. signature
        if compute_event_hash(event) != event["event_hash"]:
            raise EventRejection("HASH_MISMATCH", "event_hash does not match the canonical bytes")
        if not _verify_b64(event["actor_public_key"], event["signature"], event_signing_bytes(event)):
            raise EventRejection("INVALID_SIGNATURE", "signature does not verify for the actor key")

        # duplicate / replay before anything stateful
        known = self.events_by_id.get(event["event_id"])
        if known is not None:
            if known == event["event_hash"]:
                raise EventRejection("REPLAY_DETECTED", "event was already accepted")
            raise EventRejection("ID_REUSE", "event_id is attached to different bytes")

        if event["room_id"] != self.room_id:
            raise EventRejection("VALIDATION_FAILED", "event belongs to another room")

        payload = event["payload"]
        if "job_id" in payload and payload["job_id"] != event["job_id"]:
            raise EventRejection("VALIDATION_FAILED", "envelope job_id differs from payload job_id")

        etype = event["event_type"]
        actor = event["actor_public_key"]

        if etype == "job.created":
            self._check_created(event, actor, now_ms)
        else:
            job = self.jobs.get(event["job_id"])
            if job is None:
                raise EventRejection("RESOURCE_NOT_FOUND", "job does not exist")
            self._check_sequence(event, job, now_ms)
            self._check_transition(event, etype, actor, payload, job)

    def _check_temporal(self, event: Dict[str, Any], now_ms: Optional[int]):
        if now_ms is not None and abs(event["created_at_ms"] - now_ms) > self.max_clock_skew_ms:
            raise EventRejection("INVALID_TRANSITION", "created_at_ms is outside the clock-skew window")

    def _check_created(self, event, actor, now_ms):
        payload = event["payload"]
        if event["job_id"] in self.jobs:
            raise EventRejection("ID_REUSE", "job_id already exists")
        if actor != payload["owner_public_key"]:
            raise EventRejection("UNAUTHORIZED_ACTOR", "only the job owner may create the job")
        if payload["room_id"] != event["room_id"]:
            raise EventRejection("VALIDATION_FAILED", "job room differs from envelope room")
        policy = payload["policy"]
        if policy["job_id"] != event["job_id"] or policy["owner_public_key"] != actor:
            raise EventRejection("VALIDATION_FAILED", "policy must belong to this job and owner")
        if event["sequence"] != 0 or event["previous_event_hash"] is not None:
            raise EventRejection("INVALID_TRANSITION", "job.created must be sequence 0 with no previous hash")
        self._check_temporal(event, now_ms)

    def _check_sequence(self, event, job: JobState, now_ms):
        if event["sequence"] != job.next_sequence:
            code = "REPLAY_DETECTED" if event["sequence"] < job.next_sequence else "INVALID_TRANSITION"
            raise EventRejection(code, f"expected sequence {job.next_sequence}, got {event['sequence']}")
        if event["previous_event_hash"] != job.last_event_hash:
            raise EventRejection("INVALID_TRANSITION", "previous_event_hash does not match the accepted head")
        if event["created_at_ms"] < job.last_created_at_ms:
            raise EventRejection("INVALID_TRANSITION", "event precedes the preceding event in time")
        self._check_temporal(event, now_ms)

    def _check_transition(self, event, etype, actor, payload, job: JobState):
        if etype == "security.violation":
            if not (self.authority.gateway(actor, job) or self.authority.validator(actor)):
                raise EventRejection("UNAUTHORIZED_ACTOR", "only a gateway or validator may record violations")
            if payload["violation_id"] in self.namespaces["violation"]:
                raise EventRejection("ID_REUSE", "violation_id already used")
            if payload.get("action_id") and payload["action_id"] not in job.actions:
                raise EventRejection("RESOURCE_NOT_FOUND", "violation references an unknown action")
            return

        if job.status in TERMINAL_JOB_STATES:
            raise EventRejection("INVALID_TRANSITION", f"job is {job.status}; terminal jobs accept no transition")

        if etype == "job.accepted":
            if job.status != "open" or job.worker is not None:
                raise EventRejection("INVALID_TRANSITION", "job already has an acceptance")
            if actor != payload["worker_public_key"]:
                raise EventRejection("UNAUTHORIZED_ACTOR", "acceptance must be signed by the accepting worker")
            if job.expires_at_ms is not None and payload["accepted_at_ms"] > job.expires_at_ms:
                raise EventRejection("INVALID_TRANSITION", "job expired before acceptance")
            return

        if job.status == "open":
            raise EventRejection("INVALID_TRANSITION", "job has not been accepted")

        if etype == "action.proposed":
            if actor != job.worker or payload["proposer_public_key"] != actor:
                raise EventRejection("UNAUTHORIZED_ACTOR", "only the accepted worker may propose actions")
            if payload["action_id"] in self.namespaces["action"]:
                raise EventRejection("ID_REUSE", "action_id already used")
            if payload["action_sequence"] != job.next_action_sequence:
                raise EventRejection("INVALID_TRANSITION", f"expected action_sequence {job.next_action_sequence}")
            return

        if etype in DECISION_EVENTS:
            want_decision, bases = DECISION_EVENTS[etype]
            if payload["decision"] != want_decision or payload["basis"] not in bases:
                raise EventRejection("VALIDATION_FAILED", f"{etype} requires decision={want_decision} basis in {sorted(bases)}")
            if payload["decided_by_public_key"] != actor:
                raise EventRejection("UNAUTHORIZED_ACTOR", "decided_by_public_key must equal the signer")
            if payload["policy_hash"] != job.policy_hash:
                raise EventRejection("VALIDATION_FAILED", "policy_hash does not match the job policy")
            if payload["decision_id"] in self.namespaces["decision"]:
                raise EventRejection("ID_REUSE", "decision_id already used")
            state = job.actions.get(payload["action_id"])
            if state is None:
                raise EventRejection("RESOURCE_NOT_FOUND", "unknown action")
            if payload["basis"] == "human":
                if actor != job.owner:
                    raise EventRejection("UNAUTHORIZED_ACTOR", "human decisions require the job owner")
            elif payload["basis"] == "policy":
                if not self.authority.gateway(actor, job):
                    raise EventRejection("UNAUTHORIZED_ACTOR", "policy decisions require the gateway")
            else:  # validator
                if not self.authority.validator(actor):
                    raise EventRejection("UNAUTHORIZED_ACTOR", "validator decision requires a validator")
            allowed_from = {
                "action.allowed": {"proposed"},
                "action.denied": {"proposed", "pending"},
                "action.approval_required": {"proposed"},
                "action.approved": {"pending"},
                "action.rejected": {"proposed", "pending"},
            }[etype]
            if state not in allowed_from:
                raise EventRejection("INVALID_TRANSITION", f"{etype} is not valid while the action is {state}")
            return

        if etype == "action.completed":
            if actor != job.worker or payload["worker_public_key"] != actor:
                raise EventRejection("UNAUTHORIZED_ACTOR", "only the accepted worker may submit receipts")
            if not _verify_b64(payload["worker_public_key"], payload["signature"], receipt_signing_bytes(payload)):
                raise EventRejection("INVALID_SIGNATURE", "receipt signature does not verify")
            if payload["receipt_id"] in self.namespaces["receipt"]:
                raise EventRejection("REPLAY_DETECTED", "receipt already consumed")
            state = job.actions.get(payload["action_id"])
            if state is None:
                raise EventRejection("RESOURCE_NOT_FOUND", "unknown action")
            if state in ("succeeded", "failed"):
                raise EventRejection("REPLAY_DETECTED", "action already has a completion")
            if state not in ("allowed", "approved"):
                raise EventRejection("INVALID_TRANSITION", f"action is {state}; execution needs an allow or approval")
            proposal = job.action_payloads[payload["action_id"]]
            if payload["request_hash"] != hashlib.sha256(canonical_json(proposal)).hexdigest():
                raise EventRejection("HASH_MISMATCH", "receipt request_hash does not cover the proposed action")
            if payload["tool_id"] != proposal["tool_id"]:
                raise EventRejection("INVALID_TRANSITION", "receipt tool differs from the proposed tool")
            if payload["started_at_ms"] < proposal["proposed_at_ms"] or payload["completed_at_ms"] < payload["started_at_ms"]:
                raise EventRejection("INVALID_TRANSITION", "stale or out-of-order receipt times")
            return

        if etype in ("job.completed", "job.failed"):
            if actor != job.worker and not (etype == "job.failed" and actor == job.owner):
                raise EventRejection("UNAUTHORIZED_ACTOR", "only the worker may finish the job")
            if (etype == "job.completed") != (payload["status"] == "completed"):
                raise EventRejection("VALIDATION_FAILED", "result status does not match the event type")
            if etype == "job.completed":
                if job.pending_approvals:
                    raise EventRejection("INVALID_TRANSITION", "an approval is still pending")
                if any(s not in TERMINAL_ACTION_STATES for s in job.actions.values()):
                    raise EventRejection("INVALID_TRANSITION", "an action has not reached a terminal state")
            return

        raise EventRejection("VALIDATION_FAILED", f"unsupported event type {etype}")

    # ---- mutation --------------------------------------------------------

    def apply(self, event: Dict[str, Any]) -> None:
        etype, payload = event["event_type"], event["payload"]
        if etype == "job.created":
            job = JobState(
                event["job_id"], payload["owner_public_key"], policy_hash(payload["policy"]), payload.get("expires_at_ms")
            )
            self.jobs[event["job_id"]] = job
        else:
            job = self.jobs[event["job_id"]]
            if etype == "job.accepted":
                job.worker = payload["worker_public_key"]
                job.status = "accepted"
            elif etype == "action.proposed":
                job.actions[payload["action_id"]] = "proposed"
                job.action_payloads[payload["action_id"]] = copy.deepcopy(payload)
                job.next_action_sequence += 1
                self.namespaces["action"].add(payload["action_id"])
                job.status = "running" if job.status == "accepted" else job.status
            elif etype in DECISION_EVENTS:
                job.actions[payload["action_id"]] = {
                    "action.allowed": "allowed",
                    "action.denied": "denied",
                    "action.approval_required": "pending",
                    "action.approved": "approved",
                    "action.rejected": "rejected",
                }[etype]
                self.namespaces["decision"].add(payload["decision_id"])
                job.status = "awaiting_approval" if job.pending_approvals else ("running" if job.status == "awaiting_approval" else job.status)
            elif etype == "action.completed":
                job.actions[payload["action_id"]] = "succeeded" if payload["status"] == "success" else "failed"
                self.namespaces["receipt"].add(payload["receipt_id"])
            elif etype == "job.completed":
                job.status = "completed"
            elif etype == "job.failed":
                job.status = "failed"
            elif etype == "security.violation":
                self.namespaces["violation"].add(payload["violation_id"])
        job.next_sequence = event["sequence"] + 1
        job.last_event_hash = event["event_hash"]
        job.last_created_at_ms = event["created_at_ms"]
        self.events_by_id[event["event_id"]] = event["event_hash"]
        self.event_order.append(event["event_id"])

    def check_and_apply(self, event, now_ms=None):
        self.check(event, now_ms)
        self.apply(event)


def replay_block_events(ledger: JobLedger, block_events: List[Dict[str, Any]]) -> None:
    """Validate and apply a block's events in order; raises EventRejection."""
    for event in block_events:
        ledger.check_and_apply(event, now_ms=None)
