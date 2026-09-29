import hashlib
import itertools

import pytest
from ecdsa import SigningKey, SECP256k1

from consensus.pos import core
from consensus.pos.blockchain_structures import Block, Chain, Stake, Wallet, isvalidChain
from shared_blockchain_structures import SIGNATURE_HASH
from canonical import canonical_json, signing_bytes, CanonicalError
from tests.pos_helpers import make_block, make_stake, new_chain, install, resign


# ---- canonical encoding --------------------------------------------------

def test_canonical_bytes_ignore_dictionary_insertion_order():
    a = {"b": 1, "a": [3, {"y": 1, "x": 2}]}
    b = {"a": [3, {"x": 2, "y": 1}], "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert signing_bytes("d", a) == signing_bytes("d", b)


def test_canonical_rejects_non_finite_numbers():
    for bad in (float("nan"), float("inf")):
        with pytest.raises(CanonicalError):
            canonical_json({"x": bad})


def test_domain_prefix_separates_signatures():
    assert signing_bytes("one", {"a": 1}) != signing_bytes("two", {"a": 1})


def test_block_hash_survives_serialize_deserialize_cycle():
    w, chain = new_chain(blocks=2)
    block = chain[1]
    import json
    rebuilt = json.loads(json.dumps(block.to_dict(), sort_keys=True))
    assert core.canonical_json(rebuilt) == core.canonical_json(block.to_dict())


# ---- pseudo VRF ----------------------------------------------------------

def test_vrf_is_deterministic_for_key_and_seed():
    w = Wallet()
    assert core.vrf_prove(w.private_key, "seed") == core.vrf_prove(w.private_key, "seed")
    assert core.vrf_output_int(w.public_key_pem, "seed") == core.vrf_output_int(w.public_key_pem, "seed")


def test_vrf_changes_with_seed_and_key():
    w1, w2 = Wallet(), Wallet()
    assert core.vrf_output_int(w1.public_key_pem, "a") != core.vrf_output_int(w1.public_key_pem, "b")
    assert core.vrf_output_int(w1.public_key_pem, "a") != core.vrf_output_int(w2.public_key_pem, "a")
    assert core.vrf_prove(w1.private_key, "a") != core.vrf_prove(w1.private_key, "b")


def test_vrf_proof_verifies_only_for_exact_key_and_seed():
    w1, w2 = Wallet(), Wallet()
    proof = core.vrf_prove(w1.private_key, "seed")
    assert core.vrf_verify_proof(w1.public_key_pem, proof, "seed")
    assert not core.vrf_verify_proof(w1.public_key_pem, proof, "other")
    assert not core.vrf_verify_proof(w2.public_key_pem, proof, "seed")
    assert not core.vrf_verify_proof(w1.public_key_pem, b"garbage", "seed")
    assert not core.vrf_verify_proof(w1.public_key_pem, None, "seed")


def test_grinding_alternate_valid_proofs_cannot_change_the_output():
    """Randomised ECDSA yields many valid proofs; none may alter the lottery outcome."""
    w = Wallet()
    baseline = core.vrf_output_int(w.public_key_pem, "seed")
    proofs = {w.private_key.sign(core.vrf_seed_bytes("seed")) for _ in range(8)}
    assert len(proofs) > 1  # genuinely different valid signatures exist
    for proof in proofs:
        assert core.vrf_verify_proof(w.public_key_pem, proof, "seed")
        # The output has no dependency on the proof argument at all.
        assert core.vrf_output_int(w.public_key_pem, "seed") == baseline


# ---- eligibility boundary ------------------------------------------------

def test_eligibility_boundary_is_strictly_below():
    staked, total = 1, 4
    # threshold = MAX/4 exactly; output == threshold must NOT be eligible.
    threshold = core.MAX_OUTPUT // total
    assert core.is_eligible(threshold - 1, staked, total)
    assert not core.is_eligible(threshold, staked, total)
    assert not core.is_eligible(threshold + 1, staked, total)


def test_eligibility_rejects_degenerate_stake():
    assert not core.is_eligible(0, 0, 10)
    assert not core.is_eligible(0, 5, 0)
    assert not core.is_eligible(0, 11, 10)


def test_producer_live_and_chain_validators_agree(monkeypatch):
    """A block whose output is at/above the threshold is rejected by chain validation too."""
    w, chain = new_chain(blocks=2)
    assert isvalidChain(chain)
    monkeypatch.setattr(core, "is_eligible", lambda *a: False)
    assert not isvalidChain(chain)


# ---- stake snapshot ------------------------------------------------------

def test_snapshot_valid():
    a, b = Wallet(), Wallet()
    stakes = core.sort_snapshot([make_stake(a, 3), make_stake(b, 7)])
    assert core.validate_stake_snapshot(stakes, a.public_key_pem, 3) == 10


@pytest.mark.parametrize("case", ["duplicate", "forged", "zero_total", "creator_mismatch", "reordered", "float_amount", "not_staked"])
def test_snapshot_rejections(case):
    a, b = Wallet(), Wallet()
    good = core.sort_snapshot([make_stake(a, 3), make_stake(b, 7)])
    creator, declared = a.public_key_pem, 3
    if case == "duplicate":
        stakes = good + [make_stake(a, 3)]
    elif case == "forged":
        forged = make_stake(b, 7)
        forged.amt = 70
        stakes = core.sort_snapshot([make_stake(a, 3), forged])
    elif case == "zero_total":
        stakes = []
    elif case == "creator_mismatch":
        stakes, declared = good, 4
    elif case == "reordered":
        stakes = list(reversed(good))
    elif case == "float_amount":
        s = make_stake(a, 3)
        s.amt = 3.5
        stakes = [s]
    else:
        stakes, creator = good, Wallet().public_key_pem
    with pytest.raises(core.ConsensusError):
        core.validate_stake_snapshot(stakes, creator, declared)


def test_live_snapshot_requires_exact_equality():
    a, b, c = Wallet(), Wallet(), Wallet()
    stakes = [make_stake(a, 3), make_stake(b, 7)]
    full = {a.public_key_pem: 3, b.public_key_pem: 7, c.public_key_pem: 5}
    assert core.snapshot_matches(stakes, {a.public_key_pem: 3, b.public_key_pem: 7})
    assert not core.snapshot_matches(stakes, full)          # omitted staker
    assert not core.snapshot_matches(stakes + [make_stake(c, 5)], {a.public_key_pem: 3, b.public_key_pem: 7})  # extra
    assert not core.snapshot_matches(stakes, {a.public_key_pem: 3, b.public_key_pem: 8})


# ---- block hashing / equivalence ----------------------------------------

def _mutations(block, w):
    yield "proof", lambda b: setattr(b, "vrf_proof", b.vrf_proof + b"x")
    yield "seed", lambda b: setattr(b, "seed", b.seed + "x")
    yield "creator_stake", lambda b: setattr(b, "staked_amt", b.staked_amt + 1)
    yield "creator", lambda b: setattr(b, "creator", Wallet().public_key_pem)
    yield "timestamp", lambda b: setattr(b, "ts", b.ts + 1)
    yield "id", lambda b: setattr(b, "id", "other-id")
    yield "files", lambda b: b.files.update({"cid": "x"})
    yield "prev", lambda b: setattr(b, "prevHash", "0" * 64)
    yield "stake_entry", lambda b: setattr(b.stakers[0], "amt", b.stakers[0].amt + 1)


def test_every_consensus_field_changes_hash_and_breaks_signature():
    w, chain = new_chain(blocks=2)
    base = chain[1]
    assert core.verify_signature(base.creator, base.sign, str(base))
    for name, mutate in _mutations(base, w):
        w2, chain2 = new_chain(w, blocks=2)
        block = chain2[1]
        before = block.hash
        mutate(block)
        assert block.hash != before, name
        assert not core.verify_signature(w.public_key_pem, block.sign, str(block)), name


def test_transaction_ordering_changes_hash():
    from consensus.pos.blockchain_structures import Transaction
    w, chain = new_chain(blocks=1)
    r = Wallet()
    t1, t2 = Transaction(1, w.public_key_pem, r.public_key_pem), Transaction(2, w.public_key_pem, r.public_key_pem)
    for t in (t1, t2):
        t.sign = w.private_key.sign(str(t).encode())
    b1 = make_block(chain[0], w, [make_stake(w, 5)], [t1, t2], ts=chain[0].ts + 61000)
    b2 = make_block(chain[0], w, [make_stake(w, 5)], [t2, t1], ts=chain[0].ts + 61000)
    b2.id, b2.stakers = b1.id, b1.stakers
    assert b1.hash != b2.hash
    assert not b1.is_equal(b2)


def test_block_equivalence_detects_creator_difference():
    """Regression: is_equal used to compare self.creator with itself."""
    w, chain = new_chain(blocks=2)
    other = Wallet()
    twin = make_block(chain[0], other, [make_stake(other, 5)])
    twin.id, twin.ts, twin.prevHash = chain[1].id, chain[1].ts, chain[1].prevHash
    assert not chain[1].is_equal(twin)
    assert chain[1].is_equal(chain[1])


# ---- fork choice ---------------------------------------------------------

def test_fork_choice_is_order_independent():
    w, base = new_chain(blocks=1)
    a = base + [make_block(base[0], w, [make_stake(w, 5)])]
    b = base + [make_block(base[0], w, [make_stake(w, 5)])]
    install(base)
    assert core.better_chain(a, b) != core.better_chain(b, a)  # exactly one wins, deterministically
    winner_ab = a if core.better_chain(a, b) else b
    winner_ba = a if not core.better_chain(b, a) else b
    assert winner_ab is winner_ba


def test_heavier_chain_wins_and_longer_breaks_weight_tie():
    w, base = new_chain(blocks=1)
    light = base + [make_block(base[0], w, [make_stake(w, 5)])]
    heavy = base + [make_block(base[0], w, [make_stake(w, 50)])]
    assert core.better_chain(heavy, light)
    assert not core.better_chain(light, heavy)


def test_finalized_block_cannot_be_replaced_by_a_longer_fork():
    wallet, blocks = new_chain(blocks=3)
    current = install(blocks)
    current.params = core.ConsensusParams(1000, 1000, 1, 8, 0, 1)
    alternative = make_block(blocks[0], wallet, [make_stake(wallet, 5)])
    fork = [blocks[0], alternative]
    for _ in range(3):
        fork.append(make_block(fork[-1], wallet, [make_stake(wallet, 5)]))
    assert core.better_chain(fork, blocks)
    assert not current.rewrite(fork)
    assert current.chain == blocks


# ---- double signing ------------------------------------------------------

def _conflicting_pair(w, prev):
    b1 = make_block(prev, w, [make_stake(w, 5)])
    b2 = make_block(prev, w, [make_stake(w, 5)])
    b2.seed, b2.vrf_proof = b1.seed, b1.vrf_proof
    resign(b2, w)
    return b1, b2


def test_valid_double_sign_slashes_exactly_once():
    w, chain = new_chain(blocks=1)
    b1, b2 = _conflicting_pair(w, chain[0])
    c = install(chain + [b1])
    assert c.apply_double_sign_evidence(b1, b2, 1) is True
    assert c.chain[1].slash_creator and not c.chain[1].is_valid
    assert c.apply_double_sign_evidence(b1, b2, 1) is False
    assert c.apply_double_sign_evidence(b2, b1, 1) is False


def test_different_creators_is_a_normal_fork_not_double_signing():
    w, chain = new_chain(blocks=1)
    other = Wallet()
    b1 = make_block(chain[0], w, [make_stake(w, 5)])
    b2 = make_block(chain[0], other, [make_stake(other, 5)])
    b2.seed = b1.seed
    c = install(chain + [b1])
    with pytest.raises(core.ConsensusError) as e:
        c.apply_double_sign_evidence(b1, b2, 1)
    assert e.value.code == "EVIDENCE_CREATOR_MISMATCH"


def test_evidence_with_different_seed_or_identical_hash_or_bad_signature_never_slashes():
    w, chain = new_chain(blocks=1)
    b1, b2 = _conflicting_pair(w, chain[0])
    c = install(chain + [b1])

    other_seed = make_block(chain[0], w, [make_stake(w, 5)], seed="different-epoch")
    with pytest.raises(core.ConsensusError):
        c.apply_double_sign_evidence(b1, other_seed, 1)
    with pytest.raises(core.ConsensusError):
        c.apply_double_sign_evidence(b1, b1, 1)
    forged = make_block(chain[0], w, [make_stake(w, 5)])
    forged.seed, forged.vrf_proof = b1.seed, b1.vrf_proof
    forged.sign = b"\x00" * 64
    with pytest.raises(core.ConsensusError):
        c.apply_double_sign_evidence(b1, forged, 1)
    assert not c.chain[1].slash_creator


def test_evidence_at_wrong_height_never_slashes():
    w, chain = new_chain(blocks=1)
    b1, b2 = _conflicting_pair(w, chain[0])
    with pytest.raises(core.ConsensusError):
        core.validate_double_sign_evidence(b1, b2, 1, 2)


# ---- chain validation ----------------------------------------------------

def test_valid_chain_passes():
    _, chain = new_chain(blocks=3)
    assert isvalidChain(chain)


def test_chain_rejects_tampered_proof_and_stake_snapshot():
    w, chain = new_chain(blocks=2)
    chain[1].vrf_proof = core.vrf_prove(Wallet().private_key, chain[1].seed)
    resign(chain[1], w)
    assert not isvalidChain(chain)

    w, chain = new_chain(blocks=2)
    chain[1].staked_amt = 4
    resign(chain[1], w)
    assert not isvalidChain(chain)
