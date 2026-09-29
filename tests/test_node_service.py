import json
import time

import pytest

from agentguard.node_service import NodeUnavailable, Submission, SubmissionRejected
from consensus.pos import events as ev
from consensus.pos.blockchain_structures import Wallet
from consensus.pos.node_service import PosNodeService
from tests.factory import JobScript, make_solo_room, new_id


def wait_spacing(room, factor=1.3):
    time.sleep(room["peer"].params.min_block_spacing_seconds * factor)


def rejection_code(svc, event):
    with pytest.raises(SubmissionRejected) as info:
        svc.submit_event(event)
    return info.value.code


@pytest.fixture
def room(tmp_path):
    return make_solo_room(str(tmp_path), finality_depth=2)


def script_for(room, worker=None):
    return JobScript(room["manifest"]["room_id"], room["creator"], worker or Wallet(), clock=room["clock"])


def test_invalid_event_never_reaches_accepted_state(room):
    svc, peer = room["service"], room["peer"]
    changes = []
    svc.subscribe_state_changes(changes.append)
    s = script_for(room)
    good = s.created()
    bad = json.loads(json.dumps(good)); bad["payload"]["title"] = "tampered"
    assert rejection_code(svc, bad) == "HASH_MISMATCH"
    assert svc.get_event(good["event_id"]) is None and svc.get_event_state(good["event_id"]) is None
    assert peer.event_pool == [] and changes == []
    assert svc.produce_block(stake_amount=5) is None          # nothing valid to include
    assert svc.get_chain_summary(10)["height"] == 0


@pytest.mark.parametrize("attack", ["forged_signature", "unknown_field", "wrong_room", "replay", "duplicate_id"])
def test_forged_replayed_duplicate_events_never_finalize(room, attack):
    svc = room["service"]
    s = script_for(room)
    first = s.created()
    svc.submit_event(first)
    svc.produce_block(stake_amount=5)
    if attack == "forged_signature":
        forged = ev.sign_event({k: v for k, v in s.accepted().items() if k not in ("event_hash", "signature")}, Wallet().private_key)
        code = rejection_code(svc, forged)
        assert code == "INVALID_SIGNATURE"
    elif attack == "unknown_field":
        e = s.accepted(); e["extra"] = 1
        assert rejection_code(svc, e) == "VALIDATION_FAILED"
    elif attack == "wrong_room":
        other = JobScript("some-other-room", room["creator"], Wallet(), clock=room["clock"]).created()
        assert rejection_code(svc, other) == "VALIDATION_FAILED"
    elif attack == "replay":
        again = svc.submit_event(first)           # identical, already included -> idempotent, not a second inclusion
        assert again.ledger_state in ("included", "finalized")
        assert sum(1 for b in room["peer"].chain.chain for e in b.events if e["event_id"] == first["event_id"]) == 1
    else:
        changed = ev.sign_event({**{k: v for k, v in first.items() if k not in ("event_hash", "signature")},
                                 "created_at_ms": first["created_at_ms"] + 1}, room["creator"].private_key)
        assert rejection_code(svc, changed) == "ID_REUSE"
    assert room["peer"].event_pool == []
    assert len(room["peer"].ledger.events_by_id) == 1


def test_submit_include_finalize_flow_and_state_notifications(room):
    svc = room["service"]
    changes = []
    svc.subscribe_state_changes(changes.append)
    s = script_for(room)
    sub = svc.submit_event(s.created())
    assert isinstance(sub, Submission) and sub.ledger_state == "submitted"
    first_id = sub.event_id
    assert svc.get_event(first_id)["event_id"] == first_id
    assert svc.get_event_state(first_id) == "submitted"

    block = svc.produce_block(stake_amount=5)
    assert block and block["event_ids"] == [first_id]
    assert svc.get_event_state(first_id) == "included"

    for i in range(2):                          # finality_depth = 2 more blocks
        wait_spacing(room)
        svc.submit_event(s.accepted() if i == 0 else s.proposed()[0])
        assert svc.produce_block(stake_amount=5)
    assert svc.get_event_state(first_id) == "finalized"
    summary = svc.get_chain_summary(10)
    assert summary["height"] == 3 and summary["finalized_height"] == 1
    assert [b["finality"] for b in summary["blocks"]] == ["finalized", "finalized", "confirmed", "confirmed"]

    states = [c["ledger_state"] for c in changes if c.get("event_id") == first_id]
    assert states == ["submitted", "included", "finalized"]
    # get_block: by id and by hash
    detail = svc.get_block(summary["blocks"][1]["block_id"])
    assert detail["block"]["hash"] == summary["blocks"][1]["hash"] and detail["events"][0]["event_id"] == first_id
    assert svc.get_block(summary["blocks"][1]["hash"]) == detail
    assert svc.get_block(new_id()) is None


def test_resubmit_is_idempotent(room):
    svc = room["service"]
    e = script_for(room).created()
    first = svc.submit_event(e)
    again = svc.submit_event(e)
    assert again == first and len(room["peer"].event_pool) == 1


def test_pool_enforces_ordering_across_pending_events(room):
    svc = room["service"]
    s = script_for(room)
    svc.submit_event(s.created())
    assert svc.submit_event(s.accepted()).ledger_state == "submitted"       # builds on a pending event
    s.sequence += 1
    assert rejection_code(svc, s.proposed()[0]) == "INVALID_TRANSITION"


def test_read_models_are_serialisable_copies(room):
    svc = room["service"]
    s = script_for(room)
    a = svc.submit_event(s.created())
    svc.produce_block(stake_amount=5)
    svc.submit_event(s.accepted())
    events = svc.list_job_events(s.job_id)
    assert [e["sequence"] for e in events] == [0, 1]
    events[0]["payload"]["title"] = "mutated by caller"
    assert svc.get_event(a.event_id)["payload"]["title"] == "t"
    assert svc.list_job_events(new_id()) == []
    block = svc.get_block(svc.get_chain_summary(5)["blocks"][-1]["block_id"])
    block["events"][0]["payload"]["title"] = "x"
    assert svc.get_event(a.event_id)["payload"]["title"] == "t"
    json.dumps([svc.get_chain_summary(5), svc.get_stake_snapshot(), svc.get_peer_summaries()])


def test_chain_peer_and_stake_read_models(room):
    svc, peer = room["service"], room["peer"]
    summary = svc.get_chain_summary(5)
    assert summary["height"] == 0 and summary["blocks"][0]["previous_hash"] == "0" * 64
    assert svc.get_peer_summaries() == []
    peer.register_stake(5)
    snap = svc.get_stake_snapshot()
    assert snap["total_stake"] == 5 and snap["items"][0]["amount"] == 5
    assert snap["latest_proposer_fingerprint"] is None


def test_subscription_cancel(room):
    svc = room["service"]
    seen = []
    cancel = svc.subscribe_state_changes(seen.append)
    s = script_for(room)
    svc.submit_event(s.created())
    assert seen and all("ledger_state" in c or "kind" in c for c in seen)
    cancel()
    n = len(seen)
    svc.submit_event(s.accepted())
    assert len(seen) == n


def test_reorg_returns_orphaned_events_to_the_pool_or_rejects_them(room, tmp_path):
    """A heavier competing chain without our event: the event is submitted again (not lost, not finalized)."""
    from consensus.pos.blockchain_structures import Chain
    from tests.pos_helpers import make_stake, resign
    from tests.factory import make_node, FakeClock
    svc, peer, creator = room["service"], room["peer"], room["creator"]
    s = script_for(room)
    changes = []
    svc.subscribe_state_changes(changes.append)
    sub = svc.submit_event(s.created())
    svc.produce_block(stake_amount=5)
    assert svc.get_event_state(sub.event_id) == "included"

    from tests.test_live_validation import make_block
    genesis = peer.chain.chain[0]
    rival = make_block(genesis, creator, [make_stake(creator, 900)], ts=int(time.time() * 1000))   # heavier stake, no events
    chain = Chain(genesis_block=genesis); chain.params = peer.params; chain.chain.append(rival)
    assert peer.chain.rewrite(chain.chain) is True
    peer.rebuild_ledger()
    assert svc.get_event_state(sub.event_id) == "submitted"
    assert [c["ledger_state"] for c in changes if c.get("event_id") == sub.event_id][-1] == "submitted"


def test_no_room_means_node_unavailable(tmp_path):
    svc = PosNodeService(lambda: None)
    with pytest.raises(NodeUnavailable):
        svc.submit_event({})
    assert svc.get_event("x") is None and svc.list_job_events("x") == [] and svc.get_block("x") is None
    assert svc.get_chain_summary(1)["blocks"] == [] and svc.get_peer_summaries() == []


def test_authority_hook_controls_who_may_decide(tmp_path):
    outsider = Wallet()
    from consensus.pos.events import Authority
    from tests.factory import make_manifest, make_node, FakeClock
    creator = Wallet(); clock = FakeClock()
    manifest = make_manifest(creator)
    peer, svc = make_node(manifest, creator, str(tmp_path), clock=clock,
                          authority=Authority(is_gateway=lambda key, job: key == outsider.public_key_pem))
    s = JobScript(manifest["room_id"], creator, Wallet(), gateway=outsider, clock=clock)
    assert svc.submit_event(s.created()).ledger_state == "submitted"
    assert svc.submit_event(s.accepted()).ledger_state == "submitted"
    e, aid = s.proposed()
    assert svc.submit_event(e).ledger_state == "submitted"
    assert svc.submit_event(s.allowed(aid)).ledger_state == "submitted"     # outsider is the gateway
    with s.probe():
        by_worker = s.decision(aid, "action.denied", decision="deny", basis="policy", actor=s.worker)
    assert rejection_code(svc, by_worker) == "UNAUTHORIZED_ACTOR"
