"""Live block / chain-sync validation through the real Peer message handlers (no sockets)."""
import base64
import time

import pytest

from consensus.pos import core
from consensus.pos.blockchain_structures import Chain, Wallet, isvalidChain
from consensus.pos.mal_node import Peer as MalPeer
from consensus.pos.p2p import Peer
from tests.factory import make_manifest, make_node
from tests.pos_helpers import make_stake, resign


def pay(sender, receiver_pem, amount=1):
    from consensus.pos.blockchain_structures import Transaction
    tx = Transaction(amount, sender.public_key_pem, receiver_pem)
    tx.sign = sender.private_key.sign(str(tx).encode())
    return tx


def make_block(prev, creator, stakes, ts=None, seed=None, transactions=None):
    """pos_helpers.make_block, carrying one real payment (empty blocks are not propagated)."""
    from tests.pos_helpers import make_block as _make
    txs = transactions if transactions is not None else [pay(creator, Wallet().public_key_pem)]
    return _make(prev, creator, stakes, transactions=txs, ts=ts, seed=seed)


def now_ms():
    return int(time.time() * 1000)


def build_room(tmp_path, wallets, amount=1000):
    creator = wallets[0]
    manifest = make_manifest(creator, epoch_ms=2000, allocations=[
        {"public_key": w.public_key_pem, "amount": amount} for w in wallets])
    nodes = [make_node(manifest, w, str(tmp_path), name=f"n{i}")[0] for i, w in enumerate(wallets)]
    return manifest, nodes


def block_packet(block):
    return {"type": "new_block", "id": "blk-" + block.id, "block": block.to_dict(),
            "vrf_proof": base64.b64encode(block.vrf_proof).decode(), "sign": base64.b64encode(block.sign).decode()}


def set_epoch(peer, stakes):
    peer.current_stakers = {s.staker: s.amt for s in stakes}
    peer.current_stakes = set(stakes)


def room_for(tmp_path, others, own, other_total, want_eligible=True, extra_creators=()):
    """
    Build a room whose first allocation goes to a wallet that does (or does not)
    win the lottery for the room's genesis epoch seed with `own` of
    `own + other_total` stake. The seed depends on the manifest, so wallets are
    drawn until the property holds. Returns (winner, manifest, peers).
    """
    from consensus.pos.manifest import genesis_hash
    while True:
        w = Wallet()
        manifest = make_manifest(w, epoch_ms=2000, allocations=[
            {"public_key": x.public_key_pem, "amount": 2000,
             "stake": own if x is w else (other_total if i == 1 else 0)} for i, x in enumerate([w] + list(others))])
        seed = genesis_hash(manifest)
        if core.is_eligible(core.vrf_output_int(w.public_key_pem, seed), own, own + other_total) == want_eligible:
            break
    peers = [make_node(manifest, x, str(tmp_path), name=f"n{i}")[0] for i, x in enumerate([w] + list(others))]
    return w, manifest, peers


async def test_valid_block_accepted(tmp_path):
    b = Wallet()
    winner, manifest, (pw, peer_b) = room_for(tmp_path, [b], 900, 100)
    stakes = core.sort_snapshot([make_stake(winner, 900), make_stake(b, 100)])
    set_epoch(peer_b, stakes)
    good = make_block(peer_b.chain.chain[0], winner, stakes, ts=now_ms())
    await peer_b.handle_messages(None, block_packet(good))
    assert len(peer_b.chain.chain) == 2 and peer_b.chain.lastBlock.hash == good.hash


async def test_block_omitting_an_authenticated_staker_is_rejected(tmp_path):
    b = Wallet()
    winner, manifest, (pw, peer_b) = room_for(tmp_path, [b], 1000, 1)
    full = core.sort_snapshot([make_stake(winner, 1000), make_stake(b, 1)])
    set_epoch(peer_b, full)
    # the creator drops every other staker from its snapshot to inflate its odds
    stripped = make_block(peer_b.chain.chain[0], winner, [make_stake(winner, 1000)], ts=now_ms())
    await peer_b.handle_messages(None, block_packet(stripped))
    assert len(peer_b.chain.chain) == 1
    # control: the same creator with the complete snapshot is accepted
    complete = make_block(peer_b.chain.chain[0], winner, full, ts=now_ms())
    await peer_b.handle_messages(None, block_packet(complete))
    assert len(peer_b.chain.chain) == 2


async def test_ineligible_block_rejected_by_live_validator(tmp_path):
    b = Wallet()
    loser, manifest, (pl, peer_b) = room_for(tmp_path, [b], 1, 1000, want_eligible=False)
    stakes = core.sort_snapshot([make_stake(loser, 1), make_stake(b, 1000)])
    set_epoch(peer_b, stakes)
    lucky = make_block(peer_b.chain.chain[0], loser, stakes, ts=now_ms())
    await peer_b.handle_messages(None, block_packet(lucky))
    assert len(peer_b.chain.chain) == 1


async def test_mutated_proof_or_seed_or_declared_stake_rejected(tmp_path):
    b = Wallet()
    winner, manifest, (pw, peer_b) = room_for(tmp_path, [b], 1000, 1)
    stakes = core.sort_snapshot([make_stake(winner, 1000), make_stake(b, 1)])
    set_epoch(peer_b, stakes)
    base = peer_b.chain.chain[0]

    wrong_proof = make_block(base, winner, stakes, ts=now_ms())
    wrong_proof.vrf_proof = core.vrf_prove(Wallet().private_key, wrong_proof.seed); resign(wrong_proof, winner)
    wrong_seed = make_block(base, winner, stakes, ts=now_ms(), seed="not-the-epoch-seed")
    inflated = make_block(base, winner, stakes, ts=now_ms())
    inflated.staked_amt = 5000; resign(inflated, winner)
    for bad in (wrong_proof, wrong_seed, inflated):
        await peer_b.handle_messages(None, block_packet(bad))
        assert len(peer_b.chain.chain) == 1
    good = make_block(base, winner, stakes, ts=now_ms())          # control
    await peer_b.handle_messages(None, block_packet(good))
    assert len(peer_b.chain.chain) == 2


async def test_double_signing_across_peers_slashes_exactly_once(tmp_path):
    b, c = Wallet(), Wallet()
    cheater, manifest, (n0, nb, nc) = room_for(tmp_path, [b, c], 1000, 0)
    stakes = core.sort_snapshot([make_stake(cheater, 1000)])
    g = nb.chain.chain[0]
    b1 = make_block(g, cheater, stakes, ts=now_ms())
    b2 = make_block(g, cheater, stakes, ts=now_ms() + 1)
    assert b1.seed == b2.seed and b1.hash != b2.hash
    for peer, blk in ((nb, b1), (nc, b2)):
        set_epoch(peer, stakes)
        await peer.handle_messages(None, block_packet(blk))
        assert peer.chain.lastBlock.hash == blk.hash

    # peers exchange chains; same creator + same height + same seed => evidence
    await nb.handle_messages(None, {"type": "chain", "id": "c1", "chain": nc.chain.to_block_dict_list()})
    assert nb.chain.chain[1].slash_creator and not nb.chain.chain[1].is_valid
    bal_after_first = nb.chain.calc_balance(cheater.public_key_pem)
    await nb.handle_messages(None, {"type": "chain", "id": "c2", "chain": nc.chain.to_block_dict_list()})
    assert nb.chain.calc_balance(cheater.public_key_pem) == bal_after_first
    assert len(nb.chain.slashed_keys) == 1


async def test_different_creators_at_same_height_is_a_normal_fork(tmp_path):
    w2 = Wallet()
    w1, manifest, (n0, nb) = room_for(tmp_path, [w2], 1000, 0)
    g = nb.chain.chain[0]
    s1, s2 = [make_stake(w1, 1000)], [make_stake(w2, 1000)]
    b1 = make_block(g, w1, s1, ts=now_ms()); b2 = make_block(g, w2, s2, ts=now_ms())
    set_epoch(nb, s1)
    await nb.handle_messages(None, block_packet(b1))
    assert len(nb.chain.chain) == 2
    other = Chain(genesis_block=g); other.params = nb.params; other.chain.append(b2)
    await nb.handle_messages(None, {"type": "chain", "id": "f1", "chain": other.to_block_dict_list()})
    assert nb.chain.slashed_keys == set()
    assert not any(blk.slash_creator for blk in nb.chain.chain)


def test_malicious_peer_only_overrides_the_attack():
    assert issubclass(MalPeer, Peer)
    overridden = {name for name in vars(MalPeer) if not name.startswith("__")}
    assert "handle_messages" not in overridden and "block_dict_to_block" not in overridden
    assert "create_blocks" in overridden
