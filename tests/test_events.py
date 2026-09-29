import copy

import pytest

from consensus.pos import events as ev
from consensus.pos.blockchain_structures import Wallet
from consensus.pos.events import EventRejection, JobLedger
from tests.factory import FakeClock, JobScript, new_id

ROOM = "room-under-test"


def ledger(clock=None):
    return JobLedger(ROOM, max_clock_skew_ms=5_000, max_event_bytes=64_000)


def script(clock=None):
    return JobScript(ROOM, Wallet(), Wallet(), clock=clock or FakeClock())


def accepted_ledger(s=None):
    s = s or script()
    L = ledger()
    for e in (s.created(), s.accepted()):
        L.check_and_apply(e)
    return L, s


def code(L, event, now=None):
    with pytest.raises(EventRejection) as info:
        L.check(event, now)
    return info.value.code


def test_full_valid_lifecycle():
    L, s = accepted_ledger()
    e, aid = s.proposed(); L.check_and_apply(e)
    L.check_and_apply(s.allowed(aid))
    L.check_and_apply(s.completed(aid))
    L.check_and_apply(s.finished())
    assert L.jobs[s.job_id].status == "completed"


def test_human_approval_path():
    L, s = accepted_ledger()
    e, aid = s.proposed(); L.check_and_apply(e)
    L.check_and_apply(s.decision(aid, "action.approval_required", decision="approval_required", basis="policy"))
    assert L.jobs[s.job_id].status == "awaiting_approval"
    with s.probe():
        premature = s.finished()
    with pytest.raises(EventRejection):  # job cannot complete while approval pending
        L.check(premature)
    L.check_and_apply(s.decision(aid, "action.approved", decision="approved", basis="human"))
    L.check_and_apply(s.completed(aid))
    L.check_and_apply(s.finished())


# ---- validation order / integrity -----------------------------------------

def test_schema_violation():
    L, s = accepted_ledger()
    e, _ = s.proposed()
    e["unexpected"] = 1
    assert code(L, e) == "VALIDATION_FAILED"


def test_hash_mismatch_and_bad_signature():
    L, s = accepted_ledger()
    e, _ = s.proposed()
    tampered = copy.deepcopy(e); tampered["payload"]["arguments"] = {"x": 1}
    assert code(L, tampered) == "HASH_MISMATCH"
    forged = ev.sign_event({k: v for k, v in e.items() if k not in ("event_hash", "signature")}, Wallet().private_key)
    assert code(L, forged) == "INVALID_SIGNATURE"   # signed by a key that is not the declared actor


def test_oversize_event_rejected_before_schema():
    L = JobLedger(ROOM, 5_000, max_event_bytes=200)
    s = script()
    assert code(L, s.created()) == "PAYLOAD_TOO_LARGE"


def test_wrong_room_rejected():
    L = ledger()
    s = JobScript("another-room", Wallet(), Wallet())
    assert code(L, s.created()) == "VALIDATION_FAILED"


# ---- duplicate / replay ----------------------------------------------------

def test_duplicate_event_is_replay_and_changed_bytes_is_id_reuse():
    L, s = accepted_ledger()
    e, _ = s.proposed(); L.check_and_apply(e)
    assert code(L, e) == "REPLAY_DETECTED"
    reused = ev.sign_event({**{k: v for k, v in e.items() if k not in ("event_hash", "signature")},
                            "created_at_ms": e["created_at_ms"] + 1}, s.worker.private_key)
    assert code(L, reused) == "ID_REUSE"


def test_skipped_repeated_and_misordered_sequences():
    L, s = accepted_ledger()
    e1, a1 = s.proposed()
    skipped = copy.deepcopy(e1)
    s2 = script()
    L2, s2 = accepted_ledger(s2)
    s2.sequence += 1                    # skip one
    e_skip, _ = s2.proposed()
    assert code(L2, e_skip) == "INVALID_TRANSITION"
    L.check_and_apply(e1)
    stale = ev.sign_event({**{k: v for k, v in e1.items() if k not in ("event_hash", "signature", "event_id")},
                           "event_id": new_id()}, s.worker.private_key)
    assert code(L, stale) == "REPLAY_DETECTED"   # sequence already consumed


def test_wrong_previous_hash():
    L, s = accepted_ledger()
    s.previous_hash = "f" * 64
    e, _ = s.proposed()
    assert code(L, e) == "INVALID_TRANSITION"


def test_stale_event_outside_clock_skew():
    clock = FakeClock()
    s = script(clock)
    L = ledger()
    e = s.created()
    assert code(L, e, now=clock() + 60_000) == "INVALID_TRANSITION"
    L.check(e, now_ms=clock())


def test_event_may_not_precede_previous_event():
    L, s = accepted_ledger()
    s.clock.ms -= 10_000
    e, _ = s.proposed()
    assert code(L, e) == "INVALID_TRANSITION"


def test_replayed_receipt_and_completion():
    L, s = accepted_ledger()
    e, aid = s.proposed(); L.check_and_apply(e)
    L.check_and_apply(s.allowed(aid))
    first = s.completed(aid, receipt_id=new_id())
    L.check_and_apply(first)
    with s.probe():
        again = s.completed(aid, receipt_id=first["payload"]["receipt_id"])
    with s.probe():
        fresh_receipt = s.completed(aid)
    assert code(L, again) == "REPLAY_DETECTED"
    assert code(L, fresh_receipt) == "REPLAY_DETECTED"    # action already has a completion


# ---- authorization / transitions --------------------------------------------

def test_only_owner_creates_and_only_worker_proposes():
    s = script()
    L = ledger()
    forged_owner = s.created()
    forged_owner = ev.sign_event({**{k: v for k, v in forged_owner.items() if k not in ("event_hash", "signature")}},
                                 Wallet().private_key)
    forged_owner["actor_public_key"] = Wallet().public_key_pem   # signer is not the payload owner
    assert code(L, forged_owner) in ("HASH_MISMATCH", "INVALID_SIGNATURE")
    L2, s2 = accepted_ledger()
    intruder = Wallet()
    s2.worker = intruder
    e, _ = s2.proposed()
    assert code(L2, e) == "UNAUTHORIZED_ACTOR"


def test_human_decision_requires_owner():
    L, s = accepted_ledger()
    e, aid = s.proposed(); L.check_and_apply(e)
    L.check_and_apply(s.decision(aid, "action.approval_required", decision="approval_required", basis="policy"))
    forged = s.decision(aid, "action.approved", decision="approved", basis="human", actor=Wallet())
    assert code(L, forged) == "UNAUTHORIZED_ACTOR"


def test_decision_mismatching_event_name_rejected():
    L, s = accepted_ledger()
    e, aid = s.proposed(); L.check_and_apply(e)
    bad = s.decision(aid, "action.allowed", decision="deny", basis="policy")
    assert code(L, bad) == "VALIDATION_FAILED"


def test_execution_without_allow_is_invalid_transition():
    L, s = accepted_ledger()
    e, aid = s.proposed(); L.check_and_apply(e)
    with s.probe():
        early = s.completed(aid)
    assert code(L, early) == "INVALID_TRANSITION"
    L.check_and_apply(s.decision(aid, "action.denied", decision="deny", basis="policy"))
    with s.probe():
        late = s.completed(aid)
    assert code(L, late) == "INVALID_TRANSITION"


def test_receipt_must_cover_the_proposal():
    L, s = accepted_ledger()
    e, aid = s.proposed(); L.check_and_apply(e)
    L.check_and_apply(s.allowed(aid))
    s.actions[aid] = {**s.actions[aid], "arguments": {"tampered": True}}   # receipt over different request
    assert code(L, s.completed(aid)) == "HASH_MISMATCH"


def test_terminal_job_rejects_transitions_but_records_violations():
    L, s = accepted_ledger()
    L.check_and_apply(s.finished("failed"))
    e, _ = s.proposed()
    assert code(L, e) == "INVALID_TRANSITION"
    s.sequence, s.previous_hash = L.jobs[s.job_id].next_sequence, L.jobs[s.job_id].last_event_hash
    L.check_and_apply(s.violation())


def test_single_acceptance_and_acceptance_before_actions():
    s = script(); L = ledger()
    L.check_and_apply(s.created())
    with s.probe():
        early, _ = s.proposed()
    assert code(L, early) == "INVALID_TRANSITION"          # not accepted yet
    L.check_and_apply(s.accepted())
    second = JobScript(ROOM, s.owner, Wallet())
    second.job_id, second.policy = s.job_id, s.policy
    second.sequence, second.previous_hash = s.sequence, s.previous_hash
    assert code(L, second.accepted()) == "INVALID_TRANSITION"


def test_action_sequence_must_be_contiguous():
    L, s = accepted_ledger()
    s.action_count = 3
    e, _ = s.proposed()
    assert code(L, e) == "INVALID_TRANSITION"


def test_unknown_job_and_id_reuse_of_job():
    L = ledger()
    s = script()
    s.created(); s.accepted()          # never applied
    e, _ = s.proposed()
    assert code(L, e) == "RESOURCE_NOT_FOUND"
    L2, s2 = accepted_ledger()
    dup = JobScript(ROOM, s2.owner, s2.worker); dup.job_id = s2.job_id
    dup.policy = s2.policy
    assert code(L2, dup.created()) == "ID_REUSE"


def test_failed_check_leaves_ledger_untouched():
    L, s = accepted_ledger()
    before = copy.deepcopy(L.jobs[s.job_id].__dict__), list(L.event_order)
    e, aid = s.proposed()
    bad = copy.deepcopy(e); bad["payload"]["arguments"] = {"z": 1}
    with pytest.raises(EventRejection):
        L.check_and_apply(bad)
    assert (L.jobs[s.job_id].__dict__, L.event_order) == before
