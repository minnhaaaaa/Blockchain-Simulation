"""
Malicious PoA peer.

Formerly a 1400-line copy of consensus/poa/p2p.py that had not received the
validation hardening. It now subclasses the honest Peer and overrides only the
attack, so malicious mode changes what this node *does*, never how it
validates what it receives.

Attack: when it is this node's turn to mine, build two different blocks for
the same height (double mining) and send each to half of the peers.
"""
import asyncio, json, uuid

from consensus.poa.blockchain_structures import Transaction, Block, Chain
from consensus.poa.p2p import Peer as HonestPeer, normalize_endpoint


class Peer(HonestPeer):
    def build_conflicting_blocks(self, transaction_list):
        """Two valid-looking, mutually exclusive blocks on the current tip."""
        receivers = list(self.name_to_public_key_dict.values())
        if len(receivers) < 2:
            return None
        miners_list = self.get_current_miners_list()
        blocks = []
        for receiver in receivers[:2]:
            balance = Chain.instance.calc_balance(self.wallet.public_key_pem, self.mem_pool)
            amount = int(balance * 3 // 4)
            txs = list(transaction_list)
            if amount > 0:
                tx = Transaction(amount, self.wallet.public_key_pem, receiver)
                tx.sign = self.wallet.private_key.sign(str(tx).encode())
                txs.append(tx)
            block = Block(Chain.instance.lastBlock.hash, txs)
            block.files = self.file_hashes.copy()
            block.miner_node_id = self.node_id
            block.miner_public_key = self.wallet.public_key_pem
            block.miners_list = miners_list
            block.authority_updates = self.pending_authority_updates()
            self.sign_block(block)
            blocks.append(block)
        return blocks

    async def _send_to(self, ws, pkt):
        try:
            await ws.send(json.dumps(pkt))
        except Exception as e:
            print(f"Error broadcasting: {e}")
            if ws in self.server_connections:
                self.server_connections.discard(ws)
            else:
                endpoint = normalize_endpoint((ws.remote_address[0], ws.remote_address[1]))
                self.client_connections.discard(ws)
                self.outbound_peers.discard(endpoint)
                self.got_pong.pop(ws, None)
                self.have_sent_peer_info.pop(ws, None)
            await ws.close()
            await ws.wait_closed()

    async def mine_blocks(self):
        try:
            while True:
                for _ in range(6):
                    await asyncio.sleep(5)
                miners_list = self.get_current_miners_list()
                if not miners_list:
                    continue
                if self.node_id != miners_list[(len(Chain.instance.chain) + self.round) % len(miners_list)]:
                    continue
                async with self.mem_pool_condition:
                    pending = [t for t in self.mem_pool if not Chain.instance.transaction_exists_in_chain(t)]
                    if not pending:
                        continue
                    blocks = self.build_conflicting_blocks(pending)
                    if not blocks:
                        continue
                    Chain.instance.chain.append(blocks[0])
                    packets = [{"type": "new_block", "id": str(uuid.uuid4()), "block": b.to_dict()} for b in blocks]
                    for pkt in packets:
                        self.seen_message_ids.add(pkt["id"])
                    targets = list(self.server_connections | self.client_connections)
                    half = len(targets) // 2
                    for ws in targets[:half]:
                        await self._send_to(ws, packets[0])
                    for ws in targets[half:]:
                        await self._send_to(ws, packets[1])
                    if self.activate_disk_save == "y":
                        self.save_chain_to_disk()
        except asyncio.CancelledError:
            raise
