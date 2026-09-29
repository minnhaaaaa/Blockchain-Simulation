import json, hashlib, uuid, base64
from typing import List, Dict
from datetime import datetime
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

DIFFICULTY_PREFIX = "00000"
MINER_REWARD = 6
GENESIS_ALLOCATION = 50

class Block(BaseBlock):
    # pow block doesn't require sign for checking whether a block is valid
    def __init__(self, prevHash:str, transactions:List[Transaction], ts=None, nonce=None, id=None):
        super().__init__(prevHash, transactions, ts, id)
        self.nonce=nonce or 0 
        self.miner: str=None

        

    def to_dict(self):
        # `miner` has to be part of the hashed dictionary. While it was left
        # out, the field the reward is paid to sat outside the proof of work
        # and outside the prevHash chain, so anyone relaying a block or a
        # chain could rewrite every miner field to their own public key and
        # collect every block reward without redoing any work.
        return {
            "id":self.id,
            "prevHash":self.prevHash,
            "transactions":txs_to_json_digestable_form(self.transactions),
            "ts":self.ts,
            "nonce":self.nonce,
            "miner":self.miner,
            "files":self.files
        }

    def __str__(self):
        return json.dumps(self.to_dict())
    
    @property ## Now you can access hash like this myblock.hash
    def hash(self):
        block_str=json.dumps(self.to_dict())
        return hashlib.sha256(block_str.encode()).hexdigest()

class Chain(CommonChain):
    instance =None #Class Variable

    def __init__(self, publicKey:str=None, blockList: List[Block]=None):
        """
            If we are the first node, we mine the genesis block for ouself
            otherwise we receive blockList from the bootstrap node and
            we assign that to be the chain
        """
        if Chain.instance is not None:
            return
        
        Chain.instance=self
        """
            If blocklist is given we simply make that the chain otherwise
            we create a new chain
        """

        if publicKey and not blockList:
            genesis_block = Block(None, [Transaction(GENESIS_ALLOCATION, "Genesis", publicKey)])
            super().__init__(genesis_block=genesis_block)
            self.mine(self.chain[0])
            
        elif blockList and not publicKey:
            super().__init__(block_list=blockList)

        else:
            raise ValueError("Invalid arguments")

        Chain.instance = self

    def mine(self, block:Block):
        block.nonce=0
        print("Mining...")
        
        while not block.hash.startswith(DIFFICULTY_PREFIX) :
            block.nonce+=1

        print(f"Solution Found!!! nonce = {block.nonce} hash = {block.hash}") 
        return block.nonce
   
    def rewrite(self, blockList :List[Block]):
        if len(self.chain)>=len(blockList):
            return
        
        Chain.instance.chain=blockList.copy()
              
    def isValidBlock(self, block: Block):
        #Verify Pow:
        if not block.hash.startswith(DIFFICULTY_PREFIX):
            print(f"Problem with pow hash = {block.hash} nonce={block.nonce}")
            return False

        if self.lastBlock.hash!=block.prevHash:
            print("Hash Problem")
            print(f"Actual prev hash: {self.lastBlock.hash}\nMy prev hash: {block.prevHash}")
            return False
        
        mem_pool:List[Transaction]=[]
        seen_ids=set()
        for transaction in block.transactions:
            if Chain.instance.transaction_exists_in_chain(transaction):
                print("Duplicate transaction(s)")
                return False

            # The same transaction repeated inside one block was never
            # checked, only repeats across blocks were.
            if transaction.id in seen_ids:
                print("Duplicate transaction(s) within block")
                return False
            seen_ids.add(transaction.id)

            if not verify_signature(transaction.sender, transaction.sign, str(transaction)):
                print("\nInvalid signature on transaction\n")
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
            # `pending_transactions=mem_pool or amount<0` parsed as a single
            # keyword argument, so the amount was never range checked at all
            # and a negative amount minted coins for the sender.
            if amount<=0:
                return False
            if amount>Chain.instance.calc_balance(publicKey=transaction.sender,pending_transactions=mem_pool):
                # we have to make sure the current transactions are included when checking for balance
                return False
            mem_pool.append(transaction)

        return True

    def calc_balance(self, publicKey, pending_transactions:List[Transaction]=None):
        bal=0
        valid_chain_len=valid_chain_length(len(self.chain))

        for i in range(valid_chain_len):
            for transaction in (Chain.instance.chain[i]).transactions:
                if transaction.sender==publicKey:
                    if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                        bal-=transaction.payload[-1]
                    else:
                        bal-=transaction.payload
                elif transaction.receiver==publicKey:
                    bal+=transaction.payload
            if Chain.instance.chain[i].miner==publicKey:
                bal+=MINER_REWARD #Miner reward
        
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
    
def calc_balance_block_list(block_list:List[Block], publicKey, i, pending_transactions:List[Transaction]=None):
    bal=0
    valid_chain_len=valid_chain_length(i)

    for i in range(valid_chain_len):
        for transaction in (block_list[i]).transactions:
            if transaction.sender==publicKey:
                if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                    bal-=transaction.payload[-1]
                else:
                    bal-=transaction.payload
            elif transaction.receiver==publicKey:
                bal+=transaction.payload
        if block_list[i].miner==publicKey:
            bal+=MINER_REWARD #Miner reward

    if pending_transactions:
        for transaction in pending_transactions:
            if transaction.sender==publicKey:
                if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                    bal-=transaction.payload[-1]
                else:
                    bal-=transaction.payload
    return bal

def is_valid_genesis(block:Block):
    """
        The genesis block is the root of trust for every balance in the
        chain, and it used to be skipped entirely: a peer could offer a chain
        whose genesis block handed itself any number of coins and it would be
        accepted as long as the later blocks hashed correctly.
    """
    if block.prevHash:
        print("\nGenesis block must not have a previous hash\n")
        return False
    if not block.hash.startswith(DIFFICULTY_PREFIX):
        print("\nNo POW on genesis block\n")
        return False
    if block.miner:
        print("\nGenesis block must not claim a miner reward\n")
        return False
    if len(block.transactions)!=1:
        print("\nGenesis block must hold exactly one transaction\n")
        return False
    genesis_tx=block.transactions[0]
    if genesis_tx.sender!="Genesis" or genesis_tx.payload!=GENESIS_ALLOCATION:
        print("\nInvalid genesis allocation\n")
        return False
    if block.files:
        print("\nGenesis block must not carry files\n")
        return False
    return True

def isvalidChain(blockList:List[Block]):
    if not blockList:
        return False

    if not is_valid_genesis(blockList[0]):
        return False

    for i in range(len(blockList)):
        currBlock=blockList[i]
        if(i<=0):
            continue

        if not currBlock.hash.startswith(DIFFICULTY_PREFIX):
            print("\nNo POW\n")
            return False

        if(currBlock.prevHash!=blockList[i-1].hash):
            print("\n but Prev hash is incorrect\n")
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
            if(amount<=0 or calc_balance_block_list(blockList, transaction.sender, i, mem_pool) < amount):
                return False
            mem_pool.append(transaction)

    print("No Duplicate transactions, No Inalid Signatures, No transactions with an invalid amount\n")
    return True