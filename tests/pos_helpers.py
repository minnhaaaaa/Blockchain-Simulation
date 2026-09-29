"""Builders for signed PoS structures. Every value is generated at test time."""
import time

from consensus.pos import core
from consensus.pos.blockchain_structures import Block, Chain, Stake, Transaction, Wallet, GENESIS_ALLOCATION

EPOCH_GAP_MS = 61_000


def make_stake(wallet, amt):
    stake = Stake(wallet.public_key_pem, amt)
    stake.sign = wallet.private_key.sign(str(stake).encode())
    return stake


def make_genesis(wallet, ts=None):
    genesis = Block(None, [Transaction(GENESIS_ALLOCATION, "Genesis", wallet.public_key_pem)], ts=ts)
    genesis.creator = wallet.public_key_pem
    genesis.sign = wallet.private_key.sign(str(genesis).encode())
    return genesis


def make_block(prev, creator, stakes, transactions=None, chain_blocks=None, ts=None, seed=None):
    """A correctly proven and signed block extending `prev`."""
    block = Block(prev.hash, list(transactions or []), ts=ts or prev.ts + EPOCH_GAP_MS)
    block.creator = creator.public_key_pem
    block.stakers = list(stakes)
    block.staked_amt = next(s.amt for s in stakes if s.staker == creator.public_key_pem)
    block.seed = seed if seed is not None else prev.hash
    block.vrf_proof = core.vrf_prove(creator.private_key, block.seed)
    block.sign = creator.private_key.sign(str(block).encode())
    return block


def resign(block, wallet):
    block.sign = wallet.private_key.sign(str(block).encode())
    return block


def new_chain(wallet=None, blocks=1):
    """Chain of `blocks` blocks (genesis included) solo-staked by one wallet."""
    wallet = wallet or Wallet()
    past = int(time.time() * 1000) - 60 * 60 * 1000
    chain = [make_genesis(wallet, ts=past)]
    for _ in range(blocks - 1):
        chain.append(make_block(chain[-1], wallet, [make_stake(wallet, 5)]))
    return wallet, chain


def install(chain_blocks):
    return Chain(blockList=list(chain_blocks))
