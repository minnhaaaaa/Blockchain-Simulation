"""
Malicious PoS peer.

This used to be a 1500-line copy of consensus/pos/p2p.py whose validation
paths drifted from the honest ones. It now subclasses the honest Peer and
overrides only the attack, so malicious mode changes what this node *does*,
never how it validates what it receives.

Attack: after winning the stake lottery, sign two different blocks for the
same height and epoch seed and send each to half of the peers (double
signing), so honest peers can gather slashable evidence.
"""
import asyncio, base64, json, uuid
from datetime import datetime

from consensus.pos import core
from consensus.pos.blockchain_structures import Transaction, Block, Chain
from consensus.pos.p2p import Peer as HonestPeer, normalize_endpoint


class Peer(HonestPeer):
    def _build_conflicting_block(self, pending_transactions, seed, vrf_proof, receiver):
        balance = self.chain.calc_balance(
            self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)
        )
        payload = int(balance * 3 // 4)
        transactions = list(pending_transactions)
        if payload > 0 and receiver:
            tx = Transaction(payload, self.wallet.public_key_pem, receiver)
            tx.sign = self.wallet.private_key.sign(str(tx).encode())
            transactions.append(tx)
        block = Block(self.chain.lastBlock.hash, transactions)
        block.files = self.file_hashes.copy()
        block.seed = seed
        block.vrf_proof = vrf_proof
        block.staked_amt = self.staked_amt
        block.creator = self.wallet.public_key_pem
        block.stakers = list(self.current_stakes)
        block.sign = self.wallet.private_key.sign(str(block).encode())
        return block

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

    async def create_blocks(self, time):
        if not self.staker:
            return
        await asyncio.sleep(time)
        if len(self.current_stakers) <= 0:
            self.last_epoch_end_ts = datetime.now()
            self.staked_amt = 0
            return

        pending = [t for t in self.mem_pool if not self.chain.transaction_exists_in_chain(t)]
        if not pending:
            self.last_epoch_end_ts = datetime.now()
            self.staked_amt = 0
            async with self.curr_stakers_condition:
                self.current_stakers.clear()
                self.current_stakes.clear()
            return

        if len(self.name_to_public_key_dict) <= 1:
            print("\nDoesn't know enough ppl\n")
            return

        async with self.curr_stakers_condition:
            seed = self.chain.epoch_seed()
            vrf_proof = core.vrf_prove(self.wallet.private_key, seed)
            output = core.vrf_output_int(self.wallet.public_key_pem, seed)
            total_stake = sum(self.current_stakers.values())
            # Same eligibility rule as the honest path: the attacker must win
            # the lottery legitimately before it can double sign.
            if not core.is_eligible(output, self.staked_amt, total_stake):
                self.staked_amt = 0
                return

            receivers = list(self.name_to_public_key_dict.values())
            block1 = self._build_conflicting_block(pending, seed, vrf_proof, receivers[0])
            block2 = self._build_conflicting_block(pending, seed, vrf_proof, receivers[1])

            self.chain.chain.append(block1)
            self.last_epoch_end_ts = datetime.now()
            for transaction in block1.transactions:
                if transaction.receiver == "deploy":
                    self.deploy_contract(transaction)

            self.staked_amt = 0
            self.current_stakers.clear()
            self.current_stakes.clear()

            packets = []
            for block in (block1, block2):
                pkt = {
                    "type": "new_block",
                    "id": str(uuid.uuid4()),
                    "block": block.to_dict(),
                    "vrf_proof": base64.b64encode(vrf_proof).decode(),
                    "sign": base64.b64encode(block.sign).decode(),
                }
                packets.append(pkt)
                self.seen_message_ids.add(pkt["id"])

            if self.activate_disk_save == "y":
                self.save_chain_to_disk()

            targets = list(self.server_connections | self.client_connections)
            half = len(targets) // 2
            for ws in targets[:half]:
                await self._send_to(ws, packets[0])
            for ws in targets[half:]:
                await self._send_to(ws, packets[1])

        self.last_epoch_end_ts = datetime.now()
        async with self.mem_pool_lock:
            for transaction in list(self.mem_pool):
                if block1.transaction_exists_in_block(transaction):
                    self.mem_pool.remove(transaction)
        async with self.file_hashes_lock:
            for h in list(self.file_hashes.keys()):
                if block1.cid_exists_in_block(h):
                    self.file_hashes.pop(h, None)
