"""Three real nodes over websockets on dynamically chosen ports, from one signed manifest."""
import asyncio
import socket

import pytest

from agentguard.node_service import SubmissionRejected

from consensus.pos import events as ev
from consensus.pos.blockchain_structures import Wallet
from consensus.pos.node_service import PosNodeService
from tests.factory import FakeClock, JobScript, make_manifest, make_node


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def until(predicate, timeout=8.0, step=0.05):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if predicate():
            return True
        await asyncio.sleep(step)
    return predicate()


class Cluster:
    def __init__(self, tmp_path, manifest, wallets):
        self.nodes = []
        for i, w in enumerate(wallets):
            peer, svc = make_node(manifest, w, str(tmp_path), name=f"n{i}", port=free_port(), clock=FakeClock())
            self.nodes.append((peer, svc, w))
        self.tasks = []

    async def start(self):
        for peer, _, _ in self.nodes:
            self.tasks.append(asyncio.create_task(peer.start(interactive=False)))
        await asyncio.sleep(0.3)
        first = self.nodes[0][0]
        for peer, _, _ in self.nodes[1:]:
            asyncio.create_task(peer.connect_to_peer("127.0.0.1", first.port))
        # full mesh so every block reaches everyone regardless of gossip forwarding
        await asyncio.sleep(0.3)
        for i, (a, _, _) in enumerate(self.nodes):
            for b, _, _ in self.nodes[i + 1:]:
                if (("127.0.0.1", b.port)) not in a.outbound_peers and a is not first:
                    asyncio.create_task(a.connect_to_peer("127.0.0.1", b.port))
        await asyncio.sleep(0.5)

    async def stop(self):
        for peer, _, _ in self.nodes:
            peer.stop()
        await asyncio.gather(*self.tasks, return_exceptions=True)


@pytest.fixture
async def cluster(tmp_path):
    creator = Wallet()
    others = [Wallet(), Wallet()]
    manifest = make_manifest(creator, epoch_ms=2000, stake_amount=25, allocations=[
        {"public_key": w.public_key_pem, "amount": 1000} for w in [creator] + others])
    c = Cluster(tmp_path, manifest, [creator] + others)
    await c.start()
    yield c, manifest
    await c.stop()


async def test_three_nodes_converge_from_the_same_signed_manifest(cluster):
    c, manifest = cluster
    heads = {peer.chain.chain[0].hash for peer, _, _ in c.nodes}
    assert len(heads) == 1                                     # identical, manifest-derived genesis

    (p0, s0, creator), (p1, s1, w1), (p2, s2, w2) = c.nodes
    job = JobScript(manifest["room_id"], creator, w1, clock=s0._clock_ms)

    sub = s0.submit_event(job.created())
    assert sub.ledger_state == "submitted"
    # the pending event gossips to the other nodes' pools
    assert await until(lambda: all(s.get_event(sub.event_id) for s in (s1, s2)))

    # the creator stakes (announced to peers) and wins the only lottery
    await p0.send_stake_announcements(25)
    assert await until(lambda: p1.current_stakers and p2.current_stakers)
    await p0.create_blocks(0)

    assert await until(lambda: all(len(p.chain.chain) == 2 for p, _, _ in c.nodes))
    assert len({p.chain.lastBlock.hash for p, _, _ in c.nodes}) == 1
    for _, svc, _ in c.nodes:
        assert svc.get_event_state(sub.event_id) == "included"
    assert all(p.event_pool == [] for p, _, _ in c.nodes)


async def test_invalid_event_is_not_gossiped_or_accepted_anywhere(cluster):
    c, manifest = cluster
    (p0, s0, creator), (p1, s1, w1), _ = c.nodes
    job = JobScript(manifest["room_id"], creator, w1, clock=s0._clock_ms)
    bad = job.created()
    bad["payload"]["title"] = "tampered after signing"
    with pytest.raises(SubmissionRejected):
        s0.submit_event(bad)
    await asyncio.sleep(0.5)
    assert all(p.event_pool == [] for p, _, _ in c.nodes)

    # a forged gossip message straight to a peer's handler is rejected as well
    await p1.handle_messages(None, {"type": "agent_event", "id": "x-1", "event": bad})
    assert p1.event_pool == []


async def test_peer_rejects_foreign_genesis_chain(cluster):
    c, manifest = cluster
    from tests.pos_helpers import new_chain
    import json
    p1 = c.nodes[1][0]
    _, foreign = new_chain(blocks=2)
    from consensus.pos.blockchain_structures import Chain
    pkt = {"type": "chain", "id": "chain-1", "chain": Chain(blockList=foreign).to_block_dict_list()}
    before = p1.chain.lastBlock.hash
    await p1.handle_messages(None, pkt)
    assert p1.chain.lastBlock.hash == before and len(p1.chain.chain) == 1


async def test_room_hello_requires_a_fresh_signed_challenge(tmp_path):
    import json
    wallet = Wallet()
    manifest = make_manifest(wallet)
    peer, _ = make_node(manifest, wallet, str(tmp_path))

    class Socket:
        def __init__(self):
            self.sent = []
            self.closed = False
        async def send(self, raw): self.sent.append(json.loads(raw))
        async def close(self): self.closed = True

    victim = Socket()
    await peer.send_room_hello(victim)
    original = victim.sent[0]["challenge"]
    forged = {"type":"room_hello", "id":"forged", "room_id":manifest["room_id"],
              "genesis_hash":peer.genesis_hash, "public_key":wallet.public_key_pem,
              "challenge":original, "signature":""}
    await peer.handle_messages(victim,forged)
    assert victim.closed and victim not in peer.admitted

    replay_target = Socket()
    await peer.send_room_hello(replay_target)
    response = {"room_id":manifest["room_id"],"genesis_hash":peer.genesis_hash,
                "public_key":wallet.public_key_pem,"challenge":original}
    from canonical import signing_bytes
    import base64
    signed = {"type":"room_hello","id":"replayed",**response,
              "signature":base64.b64encode(wallet.private_key.sign(signing_bytes("agentguard.room-hello.v1",response))).decode()}
    await peer.handle_messages(replay_target,signed)
    assert replay_target.closed and replay_target not in peer.admitted
