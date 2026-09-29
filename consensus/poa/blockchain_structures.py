import json, hashlib, uuid, base64
from typing import List, Dict
from datetime import datetime
from ecdsa import SigningKey, SECP256k1, VerifyingKey
import binascii
from shared_blockchain_structures import (
    Transaction,
    BaseBlock,
    CommonChain,
    Wallet,
    txs_to_json_digestable_form,
    transaction_exists_in_block_list,
    verify_signature
)

GAS_PRICE = 0.001 # coin per gas unit
MINER_REWARD = 6
GENESIS_ALLOCATION = 50

class Block(BaseBlock):
    def __init__(self, prevHash:str, transactions:List[Transaction], ts=None, id=None):
        super().__init__(prevHash, transactions, ts, id)
        self.miner_node_id= None
        self.miner_public_key= None
        self.signature = None # This will hold the digital signature from the miner
        self.miners_list = None # List of miner nodes

    def to_dict(self):
        return {
            "id":self.id,
            "prevHash":self.prevHash,
            "transactions":txs_to_json_digestable_form(self.transactions),
            "ts":self.ts,
            "miner_node_id":self.miner_node_id,
            "miner_public_key":self.miner_public_key,
            "miners_list":self.miners_list,
            "signature":self.signature,
            "files":self.files
        }

    def __str__(self):
        return json.dumps(self.to_dict())
    
    @property ## Now you can access hash like this myblock.hash
    def hash(self):
        block_str=json.dumps(self.to_dict())
        return hashlib.sha256(block_str.encode()).hexdigest()
      
    def get_message_to_sign(self):
        return json.dumps({
            "id": self.id,
            "ts": self.ts,
            "prevHash": self.prevHash,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "miner_node_id": self.miner_node_id,
            "miner_public_key": self.miner_public_key,
            "miners_list": self.miners_list,
            "files":self.files
        }, sort_keys=True).encode()
    
    def is_valid_signature(self):
        try:
            signature = binascii.unhexlify(self.signature)
        except Exception as e:
            print(f"Invalid block signature encoding: {e}")
            return False

        if not verify_signature(self.miner_public_key, signature, self.get_message_to_sign()):
            print("Invalid block signature")
            return False
        return True

def valid_chain_length(i):
    valid_chain_len=i # because we use zero indexing

    return valid_chain_len

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
                
        if block_list[i].miner_public_key==publicKey:
            bal+=MINER_REWARD #Miner reward
        
    if pending_transactions:
        for transaction in pending_transactions:
            if transaction.sender==publicKey:
                if transaction.receiver == "deploy" or transaction.receiver == "invoke":
                    bal-=transaction.payload[-1]
                else:
                    bal-=transaction.payload

    # Since these transactions are not part of the chain we don't add
    # the money they gained yet because it could be invalid, but we subtract
    # the amount they have given to prevent double spending before the
    # transactions are added to the chain
    
    return bal

class Chain(CommonChain):
    instance = None

    def __init__(self, publicKey=None, blockList=None):
        """
            If we are the first node, we mine the genesis block for ouself
            otherwise we receive blockList from the bootstrap node and
            we assign that to be the chain
        """
        if Chain.instance is not None:
            return

        if publicKey and not blockList:
            genesis_block = Block(None, [Transaction(GENESIS_ALLOCATION, "Genesis", publicKey)])
            super().__init__(genesis_block=genesis_block)

        elif blockList and not publicKey:
            super().__init__(block_list=blockList)

        else:
            raise ValueError("Invalid arguments")

        Chain.instance = self

    def mine(self, block:Block): # point 1
        pass
    
    def rewrite(self, blockList :List[Block]):
        if len(self.chain)>=len(blockList):
            return
        
        Chain.instance.chain=blockList.copy()
                
    def isValidBlock(self, block: Block, reqd_miner_node_id, reqd_miner_public_key):
        if block.miner_node_id != reqd_miner_node_id:
            print("Mined by malicious miner")
            return False
        if self.lastBlock.hash!=block.prevHash:
            print("Hash Problem")
            print(f"Actual prev hash: {self.lastBlock.hash}\nMy prev hash: {block.prevHash}")
            return False
        
        mem_pool=[]
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
                print("\nInvalid Signature On Transaction\n")
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
            if amount>Chain.instance.calc_balance(publicKey=transaction.sender,pending_transactions=mem_pool) or amount<=0: 
                # we have to make sure the current transactions are included when checking for balance
                return False
            mem_pool.append(transaction)

        if block.miner_public_key != reqd_miner_public_key:
            print("Invalid miner public key")
            return False
        
        if not block.is_valid_signature():
            print("\nInvalid Signature On Block\n")
            return False

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
            if Chain.instance.chain[i].miner_public_key==publicKey:
                bal+=MINER_REWARD #Miner reward
        
        # Since these transactions arevalid not part of the chain we don't add
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



# Is valid chain function
def isvalidChain(blockList:List[Block]):
    """
        Validate a chain offered by a peer.

        Proof of authority rests entirely on *who* signed each block, and that
        was never checked here: a block only had to carry a signature matching
        the public key it named itself. Any node could therefore mint a longer
        chain naming itself as the miner of every block, sign each one with its
        own key, and have honest nodes adopt it. Authority is now traced from
        the genesis block forward - each block must be signed by a node the
        previous block already listed as a miner, under the public key that
        node id was first seen with.
    """
    if not blockList:
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
    if not genesis.miners_list or genesis.miner_node_id not in genesis.miners_list:
        print("\nGenesis block must be signed by an authority it lists\n")
        return False

    # node id -> public key, bound at the first block a node signs.
    node_keys={}

    for i in range(len(blockList)):
        currBlock=blockList[i]

        if(not currBlock.is_valid_signature()):
            return False

        if not currBlock.miner_node_id or not currBlock.miner_public_key:
            print("\nBlock does not identify its miner\n")
            return False

        known_key=node_keys.get(currBlock.miner_node_id)
        if known_key is None:
            node_keys[currBlock.miner_node_id]=currBlock.miner_public_key
        elif known_key!=currBlock.miner_public_key:
            print("\nMiner node id bound to a different public key\n")
            return False

        if(i<=0):
            continue

        prev_miners=blockList[i-1].miners_list or []
        if currBlock.miner_node_id not in prev_miners:
            print("\nBlock mined by a node that was not an authority\n")
            return False

        mem_pool=[]
        seen_ids=set()
        for transaction in blockList[i].transactions:
            if transaction.sender=="Genesis":
                print("\nOnly the genesis block may mint coins\n")
                return False

            if not transaction.is_valid_signature():
                return False

            if(transaction_exists_in_block_list(blockList, transaction, i)):
                print("Duplicate transaction(s)")
                return False

            if transaction.id in seen_ids:
                print("Duplicate transaction(s) within block")
                return False
            seen_ids.add(transaction.id)

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
               
        if (blockList[i].prevHash!=blockList[i-1].hash):
            return False

    return True