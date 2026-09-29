import copy
import uuid

import pytest

from consensus.poa import authority
from consensus.poa.blockchain_structures import Block, Chain, Transaction, Wallet, isvalidChain, GENESIS_ALLOCATION


class Node:
    def __init__(self):
        self.wallet = Wallet()
        self.node_id = str(uuid.uuid4())
        self.pem = self.wallet.public_key_pem


def sign(block, node):
    block.signature = node.wallet.private_key.sign(block.get_message_to_sign()).hex()
    return block


def genesis(admin, authorities):
    g = Block(None, [Transaction(GENESIS_ALLOCATION, "Genesis", admin.pem)], ts=1)
    g.miner_node_id, g.miner_public_key = admin.node_id, admin.pem
    g.miners_list = [n.node_id for n in authorities]
    return sign(g, admin)


def next_block(chain, signer, updates=None, miners_list=None, ts=None):
    b = Block(chain[-1].hash, [], ts=ts or chain[-1].ts + 1)
    b.miner_node_id, b.miner_public_key = signer.node_id, signer.pem
    b.miners_list = miners_list if miners_list is not None else authority.authority_set_for_height(chain, len(chain))
    b.authority_updates = updates or []
    return sign(b, signer)


@pytest.fixture
def cast():
    admin, m2, attacker = Node(), Node(), Node()
    return admin, m2, attacker, [genesis(admin, [admin, m2])]


def admin_update(admin, miners, activation):
    return authority.sign_update(admin.wallet.private_key, str(uuid.uuid4()), [n.node_id for n in miners], activation)


def test_honest_chain_is_valid(cast):
    admin, m2, attacker, chain = cast
    chain.append(next_block(chain, m2))
    chain.append(next_block(chain, admin))
    assert isvalidChain(chain)


def test_authorized_miner_cannot_promote_itself_via_its_own_block(cast):
    admin, m2, attacker, chain = cast
    # m2 is a real authority but writes a new list (adding the attacker) into a block it signs
    chain.append(next_block(chain, m2, miners_list=[admin.node_id, m2.node_id, attacker.node_id]))
    assert not isvalidChain(chain)
    with pytest.raises(authority.AuthorityError) as e:
        authority.validate_block_authority(chain[:1], chain[1])
    assert e.value.code == "AUTHORITY_SET_MISMATCH"


def test_attacker_block_signed_by_non_authority_rejected(cast):
    admin, m2, attacker, chain = cast
    chain.append(next_block(chain, attacker))
    assert not isvalidChain(chain)


def test_update_signed_by_a_miner_instead_of_the_admin_is_rejected(cast):
    admin, m2, attacker, chain = cast
    forged = authority.sign_update(m2.wallet.private_key, str(uuid.uuid4()), [admin.node_id, m2.node_id, attacker.node_id], 5)
    chain.append(next_block(chain, m2, updates=[forged]))
    assert not isvalidChain(chain)
    assert not authority.verify_update(admin.pem, forged)


def test_admin_update_activates_at_declared_height_and_only_then(cast):
    admin, m2, attacker, chain = cast
    update = admin_update(admin, [admin, m2, attacker], activation=3)
    chain.append(next_block(chain, m2, updates=[update]))           # height 1 carries the update
    chain.append(next_block(chain, admin))                          # height 2: old set still applies
    assert authority.authority_set_for_height(chain, 2) == [admin.node_id, m2.node_id]

    early = next_block(chain, attacker, miners_list=[admin.node_id, m2.node_id])       # height 3 begins the new set
    assert not isvalidChain(chain + [early])                        # declares the old set at height 3 -> mismatch

    ok = next_block(chain, attacker, miners_list=[admin.node_id, m2.node_id, attacker.node_id])
    assert isvalidChain(chain + [ok])
    # ...but the attacker could not have signed at height 2
    premature = next_block(chain[:2], attacker)
    assert not isvalidChain(chain[:2] + [premature])


def test_late_update_takes_effect_after_inclusion(cast):
    admin, m2, attacker, chain = cast
    chain.append(next_block(chain, m2))
    chain.append(next_block(chain, admin))
    update = admin_update(admin, [admin, m2, attacker], activation=1)         # activation already passed
    chain.append(next_block(chain, m2, updates=[update]))
    assert authority.authority_set_for_height(chain, 3) == [admin.node_id, m2.node_id]      # inclusion height 3 itself
    assert authority.authority_set_for_height(chain + [next_block(chain, admin, miners_list=[admin.node_id, m2.node_id, attacker.node_id])], 4) \
        == [admin.node_id, m2.node_id, attacker.node_id]


def test_update_must_activate_in_the_future_and_cannot_be_replayed(cast):
    admin, m2, attacker, chain = cast
    stale = admin_update(admin, [admin, m2, attacker], activation=1)
    with pytest.raises(authority.AuthorityError) as e:
        authority.validate_block_authority(chain, next_block(chain, m2, updates=[stale]))
    assert e.value.code == "UPDATE_NOT_IN_FUTURE"

    update = admin_update(admin, [admin, m2, attacker], activation=4)
    chain.append(next_block(chain, m2, updates=[update]))
    replay = next_block(chain, admin, updates=[copy.deepcopy(update)])
    with pytest.raises(authority.AuthorityError) as e:
        authority.validate_block_authority(chain, replay)
    assert e.value.code == "UPDATE_REPLAYED"
    assert not isvalidChain(chain + [replay])


def test_tampered_update_contents_break_the_admin_signature(cast):
    admin, m2, attacker, chain = cast
    update = admin_update(admin, [admin, m2], activation=5)
    tampered = {**update, "miners_list": [admin.node_id, m2.node_id, attacker.node_id]}
    assert authority.verify_update(admin.pem, update) and not authority.verify_update(admin.pem, tampered)
    for bad in ({**update, "activation_block": 2}, {**update, "id": "other"}, {**update, "signature": "zz"}, {}, None):
        assert not authority.verify_update(admin.pem, bad)


def test_genesis_trust_anchor(cast):
    admin, m2, attacker, chain = cast
    chain.append(next_block(chain, m2))
    anchor = chain[0].hash
    assert isvalidChain(chain, anchor)
    other_admin, other_m = Node(), Node()
    foreign = [genesis(other_admin, [other_admin, other_m])]
    foreign.append(next_block(foreign, other_m))
    assert isvalidChain(foreign)                        # self-consistent
    assert not isvalidChain(foreign, anchor)            # not this network's genesis


def test_canonical_block_bytes_cover_authority_updates(cast):
    admin, m2, attacker, chain = cast
    update = admin_update(admin, [admin, m2], activation=5)
    b = next_block(chain, m2, updates=[update])
    before = b.hash
    b.authority_updates = []
    assert b.hash != before and not b.is_valid_signature()


def test_poa_malicious_peer_only_overrides_the_attack():
    from consensus.poa.mal_node import Peer as MalPeer
    from consensus.poa.p2p import Peer
    assert issubclass(MalPeer, Peer)
    overridden = {n for n in vars(MalPeer) if not n.startswith("__")}
    assert "handle_messages" not in overridden and "get_current_miners_list" not in overridden
    assert "mine_blocks" in overridden
