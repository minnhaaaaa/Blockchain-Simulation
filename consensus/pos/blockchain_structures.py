import json, hashlib, uuid, base64
from typing import List,Dict
from datetime import datetime, timedelta
from ecdsa import SigningKey, SECP256k1, VerifyingKey, BadSignatureError
from shared_blockchain_structures import (
    Transaction,
    BaseBlock,
    CommonChain,
    Wallet,
    txs_to_json_digestable_form,
    valid_chain_length,
    transaction_exists_in_block_list,
    verify_signature
)
from canonical import signing_bytes
from consensus.pos import core
from consensus.pos.events import EventRejection, replay_block_events
GAS_PRICE = 0.001 # coin per gas unit
MAX_OUTPUT=2**256
MINER_REWARD = 6
GENESIS_ALLOCATION = 50

class Stake:
    def __init__(self, staker:str, amt:int, ts=None):
        self.id=str(uuid.uuid4())
        self.staker=staker
        self.amt=amt
        self.sign:bytes=None

        self.ts=ts or datetime.now().timestamp()

    def to_dict(self):
        return {
            "id":self.id,
            "staker":self.staker,
            "amt":self.amt,
            "ts":self.ts
        }

    def __str__(self):
        return core.stake_signing_string(self.to_dict())

    def __eq__(self, other):
        return isinstance(other, Stake) and self.staker==other.staker

    def __hash__(self):
        return hash(self.staker)

class Block(BaseBlock):
    def __init__(self, prevHash:str, transactions:List[Transaction], ts=None, id=None):
        super().__init__(prevHash, transactions, ts, id)

        self.creator: str=""
        self.staked_amt=0
        self.events:List[Dict]=[]  # signed agent events, see consensus/pos/events.py
        
        self.stakers:List[Stake]=[]  # needs to be replaced everywhere with stakes
        self.seed:str=""
        self.vrf_proof:bytes=None
        self.sign: bytes=None
        self.is_valid:bool=True
        self.slash_creator=False

    def stakers_to_dict_list(self):
        stakes_dict_list:List[Dict]=[]
        for stake in core.sort_snapshot(self.stakers):
            stake_dict=stake.to_dict()
            if(stake.sign):
                stake_dict["sign"]=base64.b64encode(stake.sign).decode()
            stakes_dict_list.append(stake_dict)
        return stakes_dict_list

    def to_dict(self):
        # Every consensus-relevant field is here, so it is covered by both
        # the block hash and the creator's signature: previous hash, ordered
        # transactions, files, creator, declared stake, the complete stake
        # snapshot (ordered by staker), epoch seed, proof, timestamp and id.
        # `is_valid` / `slash_creator` are derived from double-sign evidence
        # and deliberately excluded - hashing them would rewrite the hash of
        # an already-linked block when evidence arrives.
        return {
            "id":self.id,
            "prevHash":self.prevHash,
            "transactions":txs_to_json_digestable_form(self.transactions),
            "events":self.events,
            "ts":self.ts,
            "creator":self.creator,
            "staked_amt":self.staked_amt,
            "seed":self.seed,
            "vrf_proof_b64":core.b64(self.vrf_proof),
            "stakers":self.stakers_to_dict_list(),
            "files":self.files
        }

    def to_dict_with_stakers(self):
        # Kept for callers that predate the proof living inside to_dict().
        return self.to_dict()

    def signing_bytes(self) -> bytes:
        return signing_bytes(core.DOMAIN_BLOCK, self.to_dict())

    def __str__(self):
        return self.signing_bytes().decode("utf-8")

    def is_equal(self, other):
        """Equality is the canonical signed block identity."""
        if not isinstance(other, Block):
            return False
        return self.hash==other.hash and self.sign==other.sign

    @property ## Now you can access hash like this myblock.hash
    def hash(self):
        return core.sha256_hex(self.signing_bytes())


def calc_balance_block_list(block_list:List[Block], publicKey, i, mem_pool:List[Transaction]=None, currStakes:List[Stake]=None, block_reward:int=MINER_REWARD):
    bal=0
    valid_chain_len=valid_chain_length(i)

    for i in range(valid_chain_len):
        if block_list[i].slash_creator and block_list[i].creator==publicKey:
            bal-=block_list[i].staked_amt
        if not block_list[i].is_valid:
            continue
        
        for transaction in (block_list[i]).transactions:
            if transaction.sender==publicKey:
                if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                    bal-=transaction.payload[-1]
                else:
                    bal-=transaction.payload
            elif transaction.receiver==publicKey:
                bal+=transaction.payload
        if block_list[i].creator==publicKey:
            bal+=block_reward #Miner reward
    
    for transaction in mem_pool or []:
        if transaction.sender==publicKey:
            if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                bal-=transaction.payload[-1]
            else:
                bal-=transaction.payload

    if currStakes:
        for stake in currStakes:
            if stake.staker==publicKey:
                bal-=stake.amt
    # Since these transactions are not part of the chain we don't add
    # the money they gained yet because it could be invalid, but we subtract
    # the amount they have given to prevent double spending before the
    # transactions are added to the chain
    return bal

def weight_of_chain(block_list:List[Block]):
    total_weight=0
    for block in block_list:
        for stake in block.stakers:
            total_weight+=stake.amt
    return total_weight

class Chain(CommonChain):
    def __init__(self, publicKey:str=None, privatekey=None, blockList: List[Block]=None, genesis_block: Block=None):
        """
            If we are the first node, we mine the genesis block for ouself
            otherwise we receive blockList from the bootstrap node and
            we assign that to be the chain
        """
        if genesis_block is not None and not blockList and not publicKey:
            # Room genesis derived from a verified manifest (consensus/pos/manifest.py)
            super().__init__(genesis_block=genesis_block)

        elif publicKey and not blockList:
            genesis_block=Block(None, [Transaction(GENESIS_ALLOCATION,"Genesis",publicKey)])
            genesis_block.creator=publicKey
            genesis_block.sign=privatekey.sign(str(genesis_block).encode())
            super().__init__(genesis_block=genesis_block)
                
        elif blockList and not publicKey:
            super().__init__(block_list=blockList)

        else:
            raise ValueError("Invalid arguments")

        self.slashed_keys=set()
        self.params=core.ConsensusParams.legacy()


    def to_block_dict_list(self):
        block_dict_list=[]
        for block in self.chain:
            block_dict=block.to_dict()
            if block.sign:
                block_dict["sign"]=base64.b64encode(block.sign).decode()
                
            block_dict_list.append(block_dict)
        
        return block_dict_list
    
    def rewrite(self, blockList :List[Block]):
        """Replace the chain only when the candidate has a strictly better deterministic score."""
        if not core.better_chain(blockList, self.chain):
            return False
        self.chain=blockList.copy()
        return True

    def apply_double_sign_evidence(self, block_a: "Block", block_b: "Block", height: int) -> bool:
        """
            Slash a creator for signing two different blocks for one height
            and epoch seed. Returns True the first time a piece of evidence is
            applied and False afterwards, so the penalty lands exactly once.
            Raises ConsensusError when the evidence is not valid.
        """
        key=core.validate_double_sign_evidence(block_a, block_b, height, height)
        if height<=0 or height>=len(self.chain):
            raise core.ConsensusError("EVIDENCE_HEIGHT_UNKNOWN", "no block at that height")
        on_chain=self.chain[height]
        if not (on_chain.is_equal(block_a) or on_chain.is_equal(block_b)):
            raise core.ConsensusError("EVIDENCE_NOT_ON_CHAIN", "neither block is the chain's block at that height")
        if key in self.slashed_keys:
            return False
        self.slashed_keys.add(key)
        on_chain.is_valid=False
        on_chain.slash_creator=True
        return True
    
    def isValidBlock(self, block: Block, ledger=None):
        """`ledger` is the committed event ledger; it is cloned, never mutated."""
        if self.lastBlock.hash!=block.prevHash:
            print("Hash Problem")
            print(f"Actual prev hash: {self.lastBlock.hash}\nMy prev hash: {block.prevHash}")
            return False
        if block.events:
            if ledger is None:
                return False
            try:
                replay_block_events(ledger.clone(), block.events)
            except EventRejection as e:
                print(f"\nInvalid event in block: {e}\n")
                return False
        mem_pool=[] 
        # if we don't store this then a person can send two valid transaction 
        # less than his acc balance but the sum of it could be greater 
        # than his account balance
        seen_ids=set()
        for transaction in block.transactions:
            if transaction.sender=="Genesis":
                print("\nOnly the genesis block may mint coins\n")
                return False

            if self.transaction_exists_in_chain(transaction):
                print("Duplicate transaction(s)")
                return False

            # Repeats inside a single block were never rejected.
            if transaction.id in seen_ids:
                print("Duplicate transaction(s) within block")
                return False
            seen_ids.add(transaction.id)

            if not verify_signature(transaction.sender, transaction.sign, str(transaction)):
                print("\nFake Transactions\n")
                return False

            amount = 0
            if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                if not isinstance(transaction.payload, list) or not transaction.payload:
                    return False
                amount = transaction.payload[-1]
            else:
                amount = transaction.payload
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                return False
            if amount>self.calc_balance(publicKey=transaction.sender,pending_transactions=mem_pool,current_stakes=block.stakers) or amount<=0: 
                # we have to make sure the current transactions are included when checking for balance
                return False
            mem_pool.append(transaction)

        try:
            core.validate_stake_snapshot(block.stakers, block.creator, block.staked_amt, self.params.minimum_stake)
        except core.ConsensusError as e:
            print(f"\nInvalid stake snapshot: {e}\n")
            return False
        currStakes=[]
        for stake in block.stakers:
            if stake.amt>self.calc_balance(stake.staker, mem_pool, currStakes):
                return False
            currStakes.append(stake)
        return True
 
    def calc_balance(self, publicKey, pending_transactions:List[Transaction]=None, current_stakes:List[Stake]=None):
        bal=0
        valid_chain_len=valid_chain_length(len(self.chain))

        for i in range(valid_chain_len):
            if self.chain[i].slash_creator and self.chain[i].creator==publicKey:
                bal-=self.chain[i].staked_amt
            if not self.chain[i].is_valid:
                continue
            
            for transaction in (self.chain[i]).transactions:
                if transaction.sender==publicKey:
                    if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                        bal-=transaction.payload[-1]
                    else:
                        bal-=transaction.payload
                elif transaction.receiver==publicKey:
                    bal+=transaction.payload
            if self.chain[i].creator==publicKey:
                bal+=self.params.block_reward #Miner reward

        if valid_chain_len<len(self.chain):
            for i in range(valid_chain_len, len(self.chain)):
                currBlock=self.chain[i]
                for transaction in currBlock.transactions:
                    if transaction.sender==publicKey:
                        if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                            bal-=transaction.payload[-1]
                        else:
                            bal-=transaction.payload
        
        if current_stakes:
            for stake in current_stakes:
                if stake.staker==publicKey:
                    bal-=stake.amt

        # Since these transactions are not part of the chain we don't add
        # the money they gained yet because it could be invalid, but we subtract
        # the amount they have given to prevent double spending before the
        # transactions are added to the chain
        if pending_transactions:
            for transaction in pending_transactions:
                if transaction.sender==publicKey:
                    if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                        bal-=transaction.payload[-1]
                    else:
                        bal-=transaction.payload
        return bal

    def epoch_seed(self):
        bal=0
        last_finalized_block_hash=self.chain[valid_chain_length(len(self.chain))-1].hash
        return last_finalized_block_hash

    def checkEquivalence(self, block_list:List[Block]):
        """
            Returns -1 if there is no divergence, returns index of divergence if there is any
        """
        min_len=min(len(self.chain), len(block_list))
        for i in range(min_len):
            if(not self.chain[i].is_equal(block_list[i])):
                return i
        return -1

def isvalidChain(blockList:List[Block], genesis_hash:str=None, ledger_factory=None, params=None):
    """
        `genesis_hash` anchors the chain to the room manifest: the first block
        must hash to exactly that value and is not otherwise trusted. Without
        it the legacy self-signed genesis rules apply.
        `ledger_factory` builds an empty event ledger for the room; without one
        a block that carries events is invalid.
    """
    params = params or core.ConsensusParams.legacy()
    min_spacing = params.min_block_spacing_seconds
    
    if not blockList or any(block is None for block in blockList):
        return False

    ledger=ledger_factory() if ledger_factory else None
    genesis=blockList[0]
    if genesis_hash is not None:
        if genesis.hash!=genesis_hash:
            print("\nGenesis block does not match the room manifest\n")
            return False
        if genesis.events or genesis.stakers:
            return False
    else:
        if genesis.prevHash:
            print("\nGenesis block must not have a previous hash\n")
            return False
        if len(genesis.transactions)!=1:
            print("\nGenesis block must hold exactly one transaction\n")
            return False
        genesis_tx=genesis.transactions[0]
        if genesis_tx.sender!="Genesis" or genesis_tx.payload!=GENESIS_ALLOCATION:
            print("\nInvalid genesis allocation\n")
            return False
        if genesis.stakers or genesis.events:
            print("\nGenesis block must not carry stakes or events\n")
            return False

    for i in range(len(blockList)):
        currBlock=blockList[i]
        if i==0 and genesis_hash is not None:
            continue  # trusted only because its hash equals the manifest anchor
        if not verify_signature(currBlock.creator, currBlock.sign, str(currBlock)):
            print("\nInvalid signature on block\n")
            return False
        
        if(i<=0):
            continue

        # Timestamp validation
        try:
            # Convert Unix timestamp to datetime
            if isinstance(currBlock.ts, (int, float)):
                block_time = datetime.fromtimestamp(currBlock.ts/1000)
            elif isinstance(currBlock.ts, str):
                block_time = datetime.fromisoformat(currBlock.ts)
            elif isinstance(currBlock.ts, datetime):
                block_time = currBlock.ts
            else:
                print("\nInvalid Block timestamp format\n")
                return False

            # Get previous block time
            prev_block_ts = blockList[i-1].ts
            if isinstance(prev_block_ts, (int, float)):
                prev_block_time = datetime.fromtimestamp(prev_block_ts/1000)
            elif isinstance(prev_block_ts, str):
                prev_block_time = datetime.fromisoformat(prev_block_ts)
            elif isinstance(prev_block_ts, datetime):
                prev_block_time = prev_block_ts
            else:
                print("\nInvalid previous block timestamp format\n")
                return False

            # Check block isn't from the future (allow some tolerance for clock skew)
            current_time = datetime.now()
            if block_time > current_time + timedelta(milliseconds=params.max_clock_skew_ms):
                print(f"\nBlock {i} timestamp in future\n")
                return False

            # Check blocks are in chronological order
            if block_time < prev_block_time:
                print(f"\nBlock {i} timestamp before previous block\n")
                return False

            # Verify minimum time between blocks (staking registration period)
            time_diff = (block_time - prev_block_time).total_seconds()
            if time_diff < min_spacing:
                print(f"\nBlocks {i-1} and {i} too close together: {time_diff}s < {min_spacing}s\n")
                return False

        except (ValueError, AttributeError, TypeError, OSError) as e:
            print(f"\nTimestamp validation error on block {i}: {e}\n")
            return False

        if not currBlock.vrf_proof or not core.vrf_verify_proof(currBlock.creator, currBlock.vrf_proof, currBlock.seed):
            print("\nInvalid signature on vrf_proof\n")
            return False
        
        if(str(currBlock.seed)!=str(blockList[valid_chain_length(i)-1].hash)):
            print("\nInvalid Seed\n")
            return False

        try:
            total_stake=core.validate_stake_snapshot(currBlock.stakers, currBlock.creator, currBlock.staked_amt, params.minimum_stake)
        except core.ConsensusError as e:
            print(f"\nInvalid stake snapshot: {e}\n")
            return False

        vrf_out=core.vrf_output_int(currBlock.creator, currBlock.seed)
        if not core.is_eligible(vrf_out, currBlock.staked_amt, total_stake):
            print("\nFalsified vrf\n")
            return False

        if currBlock.events:
            if ledger is None:
                print("\nBlock carries events but no room event rules are configured\n")
                return False
            try:
                replay_block_events(ledger, currBlock.events)
            except EventRejection as e:
                print(f"\nInvalid event in block: {e}\n")
                return False

        mem_pool=[]
        seen_ids=set()
        for transaction in blockList[i].transactions:
            if transaction.sender=="Genesis":
                print("\nOnly the genesis block may mint coins\n")
                return False

            if(transaction_exists_in_block_list(blockList, transaction, i)):
                print("Duplicate transaction(s)")
                return False

            if transaction.id in seen_ids:
                print("Duplicate transaction(s) within block")
                return False
            seen_ids.add(transaction.id)

            if not verify_signature(transaction.sender, transaction.sign, str(transaction)):
                print("\nInvalid signature on transaction\n")
                return False

            amount = 0
            if(transaction.receiver == "deploy" or transaction.receiver == "invoke"):
                if not isinstance(transaction.payload, list) or not transaction.payload:
                    return False
                amount = transaction.payload[-1]
            else:
                amount = transaction.payload
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                return False
            if(amount<=0 or calc_balance_block_list(blockList, transaction.sender, i, mem_pool, currBlock.stakers, params.block_reward) < amount):
                return False
            mem_pool.append(transaction)
        
        # we use a currStakes list because if we just pass currBlock.stakers then the stake 
        # which we are processing will already be there
        currStakes=[]
        for stake in currBlock.stakers:
            if stake.amt>calc_balance_block_list(blockList, stake.staker, i, mem_pool, currStakes, params.block_reward):
                return False
            currStakes.append(stake)

        
        if(calc_balance_block_list(blockList, blockList[i].creator, i, mem_pool, None, params.block_reward)<0):
            return False
        
        if (blockList[i].prevHash!=blockList[i-1].hash):
            return False

    return True

