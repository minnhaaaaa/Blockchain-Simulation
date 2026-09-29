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
        return json.dumps(self.to_dict())

    def __eq__(self, other):
        return isinstance(other, Stake) and self.staker==other.staker

    def __hash__(self):
        return hash(self.staker)

class Block(BaseBlock):
    def __init__(self, prevHash:str, transactions:List[Transaction], ts=None, id=None):
        super().__init__(prevHash, transactions, ts, id)

        self.creator: str=""
        self.staked_amt=0
        
        self.stakers:List[Stake]=[]  # needs to be replaced everywhere with stakes
        self.seed:str=""
        self.vrf_proof:bytes=None
        self.sign: bytes=None
        self.is_valid:bool=True
        self.slash_creator=False

    def stakers_to_dict_list(self):
        stakes_dict_list:List[Dict]=[]
        for stake in sorted(self.stakers, key=lambda stake: stake.id):
            stake_dict=stake.to_dict()
            if(stake.sign):
                stake_dict["sign"]=base64.b64encode(stake.sign).decode()
            stakes_dict_list.append(stake_dict)
        return stakes_dict_list

    def to_dict(self):
        # `stakers` and `seed` belong in the signed and hashed dictionary.
        # While they sat outside it, the stake set a block declared was not
        # covered by the creator's signature or by the block hash, so a relay
        # could strip it down to the creator's own stake. Both the VRF
        # threshold - staked_amt / total stake - and the heaviest chain rule
        # are computed from that set, so stripping it handed the attacker a
        # lottery they always win on a chain that always outweighs the
        # honest one.
        return {
            "id":self.id,
            "prevHash":self.prevHash,
            "transactions":txs_to_json_digestable_form(self.transactions),
            "ts":self.ts,
            "creator":self.creator,
            "staked_amt":self.staked_amt,
            "seed":self.seed,
            "stakers":self.stakers_to_dict_list(),
            "files":self.files
        }
    
    def to_dict_with_stakers(self):
        block_dict=self.to_dict()
        if(self.vrf_proof):
            block_dict["vrf_proof_b64"]=base64.b64encode(self.vrf_proof).decode()
        return block_dict


    def __str__(self):
        return json.dumps(self.to_dict())
    
    def is_equal(self, other):
        same=True
        if(len(self.transactions)!=len(other.transactions)):
            return False
        
        tx_len=len(self.transactions)
        for i in range(tx_len):
            if(self.transactions[i]!=other.transactions[i]):
                return False
            
        return(
            self.id==other.id and
            self.ts==other.ts and
            self.prevHash==other.prevHash and
            self.hash==other.hash and
            self.sign==other.sign and
            self.creator==self.creator
    )

    @property ## Now you can access hash like this myblock.hash
    def hash(self):
        block_str=json.dumps(self.to_dict())
        return hashlib.sha256(block_str.encode()).hexdigest()


def calc_balance_block_list(block_list:List[Block], publicKey, i, mem_pool:List[Transaction]=None, currStakes:List[Stake]=None):
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
            bal+=MINER_REWARD #Miner reward
    
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
    instance = None #Class Variable

    def __init__(self, publicKey:str=None, privatekey=None, blockList: List[Block]=None):
        """
            If we are the first node, we mine the genesis block for ouself
            otherwise we receive blockList from the bootstrap node and
            we assign that to be the chain
        """
        if Chain.instance is not None:
            return

        if publicKey and not blockList:
            genesis_block=Block(None, [Transaction(GENESIS_ALLOCATION,"Genesis",publicKey)])
            genesis_block.creator=publicKey
            genesis_block.sign=privatekey.sign(str(genesis_block).encode())
            super().__init__(genesis_block=genesis_block)
                
        elif blockList and not publicKey:
            super().__init__(block_list=blockList)

        else:
            raise ValueError("Invalid arguments")

        Chain.instance = self


    def to_block_dict_list(self):
        block_dict_list=[]
        for block in self.chain:
            block_dict=block.to_dict_with_stakers()
            if block.sign:
                block_dict["sign"]=base64.b64encode(block.sign).decode()
                
            block_dict_list.append(block_dict)
        
        return block_dict_list
    
    def rewrite(self, blockList :List[Block]):
        if weight_of_chain(self.chain)>=weight_of_chain(blockList):
            return
        
        Chain.instance.chain=blockList.copy()    
    
    def isValidBlock(self, block: Block):
        if self.lastBlock.hash!=block.prevHash:
            print("Hash Problem")
            print(f"Actual prev hash: {self.lastBlock.hash}\nMy prev hash: {block.prevHash}")
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

            if Chain.instance.transaction_exists_in_chain(transaction):
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
            if amount>Chain.instance.calc_balance(publicKey=transaction.sender,pending_transactions=mem_pool,current_stakes=block.stakers) or amount<=0: 
                # we have to make sure the current transactions are included when checking for balance
                return False
            mem_pool.append(transaction)

        currStakes=[]
        seen_stakers=set()
        for stake in block.stakers:
            if not verify_signature(stake.staker, stake.sign, str(stake)):
                print("\nInvalid signature on stake\n")
                return False
            # One staker counted twice in a block inflates both the total
            # stake and the weight of the chain.
            if stake.staker in seen_stakers:
                print("\nDuplicate staker in block\n")
                return False
            seen_stakers.add(stake.staker)
            if not isinstance(stake.amt, (int, float)) or isinstance(stake.amt, bool):
                return False
            if(stake.amt<=0 or stake.amt>Chain.instance.calc_balance(stake.staker, mem_pool, currStakes)):
                return False
            currStakes.append(stake)
        return True
 
    def calc_balance(self, publicKey, pending_transactions:List[Transaction]=None, current_stakes:List[Stake]=None):
        bal=0
        valid_chain_len=valid_chain_length(len(self.chain))

        for i in range(valid_chain_len):
            if Chain.instance.chain[i].slash_creator and Chain.instance.chain[i].creator==publicKey:
                bal-=Chain.instance.chain[i].staked_amt
            if not Chain.instance.chain[i].is_valid:
                continue
            
            for transaction in (Chain.instance.chain[i]).transactions:
                if transaction.sender==publicKey:
                    if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                        bal-=transaction.payload[-1]
                    else:
                        bal-=transaction.payload
                elif transaction.receiver==publicKey:
                    bal+=transaction.payload
            if Chain.instance.chain[i].creator==publicKey:
                bal+=MINER_REWARD #Miner reward

        if valid_chain_len<len(self.chain):
            for i in range(valid_chain_len, len(self.chain)):
                currBlock=Chain.instance.chain[i]
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

def isvalidChain(blockList:List[Block]):
    EPOCH_TIME = 60  # Add this constant or pass it as a parameter
    
    if not blockList or any(block is None for block in blockList):
        return False

    genesis=blockList[0]
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
    if genesis.stakers:
        print("\nGenesis block must not carry stakes\n")
        return False

    for i in range(len(blockList)):
        currBlock=blockList[i]
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
            if block_time > current_time + timedelta(seconds=10):
                print(f"\nBlock {i} timestamp in future\n")
                return False

            # Check blocks are in chronological order
            if block_time < prev_block_time:
                print(f"\nBlock {i} timestamp before previous block\n")
                return False

            # Verify minimum time between blocks (staking registration period)
            time_diff = (block_time - prev_block_time).total_seconds()
            if time_diff < EPOCH_TIME * 5/6:
                print(f"\nBlocks {i-1} and {i} too close together: {time_diff}s < {EPOCH_TIME * 5/6}s\n")
                return False

        except (ValueError, AttributeError, TypeError, OSError) as e:
            print(f"\nTimestamp validation error on block {i}: {e}\n")
            return False

        if not verify_signature(currBlock.creator, currBlock.vrf_proof, currBlock.seed):
            print("\nInvalid signature on vrf_proof\n")
            return False
        
        if(str(currBlock.seed)!=str(blockList[valid_chain_length(i)-1].hash)):
            print("\nInvalid Seed\n")
            return False

        total_stake=0
        seen_stakers=set()
        creator_stake=0
        for stake in currBlock.stakers:
            if not verify_signature(stake.staker, stake.sign, str(stake)):
                print("\nInvalid signature on stake\n")
                return False
            if stake.staker in seen_stakers:
                print("\nDuplicate staker in block\n")
                return False
            seen_stakers.add(stake.staker)
            if not isinstance(stake.amt, (int, float)) or isinstance(stake.amt, bool) or stake.amt<=0:
                return False
            if stake.staker==currBlock.creator:
                creator_stake=stake.amt
            total_stake+=stake.amt

        # A block with no stakes behind it divided by zero here, which took
        # down whichever task was validating the chain.
        if total_stake<=0:
            print("\nBlock declares no stake\n")
            return False

        # The creator's declared stake has to be the stake it actually
        # announced and signed for, otherwise it can name any figure it likes
        # and set its own odds.
        if currBlock.staked_amt!=creator_stake:
            print("\nCreator's staked amount does not match its signed stake\n")
            return False

        vrf_output=hashlib.sha256(currBlock.vrf_proof).hexdigest()
        vrf_ouput_int=int(vrf_output, 16)

        threshold=(currBlock.staked_amt/total_stake)*MAX_OUTPUT
        if(vrf_ouput_int>threshold):
            print("\nFalsified vrf\n")
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
            if(amount<=0 or calc_balance_block_list(blockList, transaction.sender, i, mem_pool, currBlock.stakers) < amount):
                return False
            mem_pool.append(transaction)
        
        # we use a currStakes list because if we just pass currBlock.stakers then the stake 
        # which we are processing will already be there
        currStakes=[]
        for stake in currBlock.stakers:
            if stake.amt>calc_balance_block_list(blockList, stake.staker, i, mem_pool, currStakes):
                return False
            currStakes.append(stake)

        
        if(calc_balance_block_list(blockList, blockList[i].creator, i, mem_pool)<0):
            return False
        
        if (blockList[i].prevHash!=blockList[i-1].hash):
            return False

    return True

