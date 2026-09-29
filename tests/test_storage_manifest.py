import json
import os

import pytest

from consensus.pos import manifest as rm
from consensus.pos.blockchain_structures import Chain, Wallet, isvalidChain
from consensus.pos.manifest import ManifestError, build_genesis, genesis_hash, verify_manifest
from storage.node_storage import LegacyStorageError, NodeStorage, StorageConfigError
from tests.factory import make_manifest, make_node, make_solo_room, FakeClock
from tests.pos_helpers import make_block, make_stake


# ---- storage isolation ------------------------------------------------------

def test_storage_requires_configuration(tmp_path):
    with pytest.raises(StorageConfigError):
        NodeStorage(None, "room-1", "node-1")
    with pytest.raises(StorageConfigError):
        NodeStorage(str(tmp_path), None, "node-1")
    for bad in ("../escape", "a/b", "", ".", ".."):
        with pytest.raises(StorageConfigError):
            NodeStorage(str(tmp_path), bad, "node-1")


def test_nodes_cannot_overwrite_each_others_identity_or_chain(tmp_path):
    a = NodeStorage(str(tmp_path), "room-1", "node-a")
    b = NodeStorage(str(tmp_path), "room-1", "node-b")
    other_room = NodeStorage(str(tmp_path), "room-2", "node-a")
    wa, wb = Wallet(), Wallet()
    a.save_key(wa.private_key_pem); b.save_key(wb.private_key_pem); other_room.save_key(Wallet().private_key_pem)
    a.save_chain([{"x": 1}]); b.save_chain([{"x": 2}])
    assert a.load_key() == wa.private_key_pem and b.load_key() == wb.private_key_pem
    assert a.load_chain() == [{"x": 1}] and b.load_chain() == [{"x": 2}]
    assert a.dir != b.dir != other_room.dir
    assert os.path.dirname(a.dir) == os.path.join(str(tmp_path), "room-1")
    assert oct(os.stat(os.path.join(a.dir, "keys.json")).st_mode & 0o777) == "0o600"


def test_legacy_unversioned_state_is_rejected_with_precise_message(tmp_path):
    s = NodeStorage(str(tmp_path), "room-1", "node-1")
    with open(os.path.join(s.dir, "chain.json"), "w") as fh:
        json.dump([{"legacy": "sha1 era"}], fh)
    with pytest.raises(LegacyStorageError) as e:
        s.load_chain()
    assert "clean network" in str(e.value)


def test_legacy_global_storage_rejects_unversioned_chain(tmp_path, monkeypatch):
    import storage.storage_manager as sm
    monkeypatch.setattr(sm, "BASE_STORAGE_DIR", str(tmp_path))
    os.makedirs(tmp_path / "pos")
    (tmp_path / "pos" / "chain.json").write_text("[]")
    with pytest.raises(sm.LegacyStorageError):
        sm.load_chain("pos")
    sm.save_chain([{"a": 1}], "pos")
    assert sm.load_chain("pos") == [{"a": 1}]


def test_manifest_is_immutable_per_room_storage(tmp_path):
    c = Wallet()
    m1, m2 = make_manifest(c, room_id="same-room-id"), make_manifest(c, room_id="same-room-id")
    s = NodeStorage(str(tmp_path), "same-room-id", "n1")
    s.save_manifest(m1)
    s.save_manifest(m1)
    with pytest.raises(StorageConfigError):
        s.save_manifest(m2)


# ---- manifest / genesis trust anchor ---------------------------------------

def test_manifest_verification():
    c = Wallet()
    m = make_manifest(c)
    assert verify_manifest(m, m["room_id"]) is m
    forged = json.loads(json.dumps(m)); forged["genesis"]["allocations"][0]["amount"] = 10 ** 9
    with pytest.raises(ManifestError) as e:
        verify_manifest(forged)
    assert e.value.code == "INVALID_SIGNATURE"
    with pytest.raises(ManifestError) as e:
        verify_manifest({**m, "extra": 1})
    assert e.value.code == "VALIDATION_FAILED"
    with pytest.raises(ManifestError):
        verify_manifest(m, "another-room-id")


def test_genesis_is_deterministic_from_manifest():
    m = make_manifest(Wallet())
    assert genesis_hash(m) == genesis_hash(json.loads(json.dumps(m)))
    assert build_genesis(m).hash == build_genesis(m).hash


def test_chain_with_valid_self_signed_but_different_genesis_is_rejected():
    creator = Wallet()
    m = make_manifest(creator)
    anchor = genesis_hash(m)
    # a perfectly valid, self-signed legacy chain that is not the room's genesis
    from tests.pos_helpers import new_chain
    _, other = new_chain(blocks=2)
    assert isvalidChain(other)                        # valid on its own terms
    assert not isvalidChain(other, anchor)            # but not this room's chain


def test_chain_built_on_manifest_genesis_validates(tmp_path):
    room = make_solo_room(str(tmp_path))
    peer, svc = room["peer"], room["service"]
    import time
    svc.produce_block(stake_amount=5) if False else None
    genesis = peer.chain.chain[0]
    block = make_block(genesis, room["creator"], [make_stake(room["creator"], 5)])
    assert isvalidChain([genesis, block], genesis_hash(room["manifest"]), params=peer.params)


def test_unanchored_genesis_with_multiple_allocations_needs_manifest():
    a, b = Wallet(), Wallet()
    m = make_manifest(a, allocations=[{"public_key": a.public_key_pem, "amount": 10}, {"public_key": b.public_key_pem, "amount": 20}])
    g = build_genesis(m)
    assert isvalidChain([g], genesis_hash(m))
    assert not isvalidChain([g])                      # legacy rules demand exactly one allocation


# ---- restart / tamper ------------------------------------------------------

def test_restart_reloads_and_revalidates_chain(tmp_path):
    import time
    from consensus.pos.p2p import Peer
    from storage.node_storage import NodeStorage
    room = make_solo_room(str(tmp_path))
    svc, peer = room["service"], room["peer"]
    from tests.factory import JobScript
    s = JobScript(room["manifest"]["room_id"], room["creator"], Wallet(), clock=room["clock"])
    svc.submit_event(s.created())
    assert svc.produce_block(stake_amount=5)
    peer.save_chain_to_disk() if False else peer.storage.save_chain(peer.chain.to_block_dict_list())

    again = Peer("127.0.0.1", 0, "again", True, "y", "n", manifest=room["manifest"], storage=peer.storage,
                 event_rules=peer.event_rules)
    assert [b.hash for b in again.chain.chain] == [b.hash for b in peer.chain.chain]
    assert len(again.ledger.events_by_id) == 1

    # tamper with the stored chain: an event edit must be refused at startup
    doc = peer.storage.load_chain()
    doc[1]["events"][0]["payload"]["title"] = "edited on disk"
    peer.storage.save_chain(doc)
    with pytest.raises(ValueError):
        Peer("127.0.0.1", 0, "again", True, "y", "n", manifest=room["manifest"], storage=peer.storage,
             event_rules=peer.event_rules)


# ---- blocks carrying events ------------------------------------------------

def test_block_event_tampering_or_duplicate_history_invalidates_chain(tmp_path):
    import copy
    from tests.factory import JobScript
    from tests.pos_helpers import resign
    room = make_solo_room(str(tmp_path))
    peer, creator, manifest = room["peer"], room["creator"], room["manifest"]
    s = JobScript(manifest["room_id"], creator, Wallet(), clock=room["clock"])
    genesis = peer.chain.chain[0]
    created = s.created()
    b1 = make_block(genesis, creator, [make_stake(creator, 5)])
    b1.events = [created]; resign(b1, creator)
    factory = peer._new_ledger
    anchor = genesis_hash(manifest)
    assert isvalidChain([genesis, b1], anchor, factory, peer.params)
    assert not isvalidChain([genesis, b1], anchor, None, peer.params)      # events but no rules

    tampered = copy.deepcopy(b1); tampered.events[0]["payload"]["title"] = "x"; resign(tampered, creator)
    assert not isvalidChain([genesis, tampered], anchor, factory, peer.params)

    b2 = make_block(b1, creator, [make_stake(creator, 5)])
    b2.events = [created]; resign(b2, creator)                              # same event again in a later block
    assert not isvalidChain([genesis, b1, b2], anchor, factory, peer.params)
