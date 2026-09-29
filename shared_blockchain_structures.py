import json, uuid, base64, hashlib, ipaddress, socket
from typing import List, Dict
from datetime import datetime
from ecdsa import VerifyingKey, SigningKey, SECP256k1
from canonical import DOMAIN_TX, signing_bytes

# ECDSA signatures are hashed with SHA-256. python-ecdsa defaults to SHA-1,
# which is collision broken and unsuitable for signing attacker-composable
# messages such as transactions and blocks.
SIGNATURE_HASH = hashlib.sha256

MAX_KNOWN_PEERS = 1024
MAX_SEEN_MESSAGE_IDS = 50000


def load_verifying_key(public_key_pem) -> VerifyingKey:
    """
        Load a PEM public key that verifies with SIGNATURE_HASH.
        Accepts str or bytes, raises on anything malformed.
    """
    if isinstance(public_key_pem, str):
        public_key_pem = public_key_pem.encode()
    return VerifyingKey.from_pem(public_key_pem, hashfunc=SIGNATURE_HASH)


def verify_signature(public_key_pem, signature, message) -> bool:
    """
        Verify `signature` over `message` under `public_key_pem`.

        Returns False instead of raising for every kind of malformed input.
        A remote peer controls all three arguments, so a narrow
        `except BadSignatureError` would let a malformed key or signature
        escape as an unhandled exception and tear down the connection task.
    """
    if not public_key_pem or signature is None or message is None:
        return False
    try:
        if isinstance(message, str):
            message = message.encode()
        load_verifying_key(public_key_pem).verify(signature, message)
        return True
    except Exception:
        return False


def remember_message_id(seen_message_ids: set, message_id: str):
    """
        Record a message id, discarding old entries once the set grows too
        large. Without a bound a peer can exhaust our memory just by
        broadcasting messages with fresh ids.
    """
    if len(seen_message_ids) >= MAX_SEEN_MESSAGE_IDS:
        for old in list(seen_message_ids)[: MAX_SEEN_MESSAGE_IDS // 2]:
            seen_message_ids.discard(old)
    seen_message_ids.add(message_id)


_endpoint_cache: Dict[str, str] = {}


def resolve_host(host) -> str:
    """
        Resolve a host to an IPv4 address.

        Peer messages carry this value, so reject anything that isn't a
        plausible host name before handing it to the resolver, and cache
        results so a peer can't make us issue unbounded blocking DNS
        lookups from inside the event loop.
    """
    if not isinstance(host, str) or not 0 < len(host) <= 253:
        raise ValueError("Invalid host")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-." for c in host):
        raise ValueError("Invalid host")
    cached = _endpoint_cache.get(host)
    if cached:
        return cached
    if len(_endpoint_cache) > MAX_KNOWN_PEERS:
        _endpoint_cache.clear()
    resolved = socket.gethostbyname(host)
    _endpoint_cache[host] = resolved
    return resolved


def validate_port(port) -> int:
    """
        Coerce a peer supplied port and reject anything out of range.
    """
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    return port


class Transaction:
    def __init__(self, payload, sender: str, receiver: str, id=None, ts=None):
        self.id=id or str(uuid.uuid4())
        self.payload=payload   # amount or [code, amount] or [contract id, function_name, arguments, state, amount]
        self.sender: str=sender  # Public Key
        self.receiver: str=receiver   # Public Key or "deploy" or "invoke"
        self.sign:bytes=None
        self.ts=ts or datetime.now().timestamp()

    def to_dict(self):
        dict={
            "id":self.id,
            "payload":self.payload,
            "sender":self.sender,
            "receiver":self.receiver,
            "ts":self.ts
        }
        return dict
    
    def __eq__(self, other):
        return(
            self.id==other.id and
            self.sender==other.sender and
            self.receiver==other.receiver and
            self.ts==other.ts
        )
    
    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        # Canonical, domain-separated signing string: dictionary insertion
        # order and relay/re-serialisation cannot change the signed bytes.
        return signing_bytes(DOMAIN_TX, self.to_dict()).decode("utf-8")
    
    def is_valid_signature(self):
        if not verify_signature(self.sender, self.sign, str(self)):
            print("Invalid transaction signature")
            return False
        return True
    
def txs_to_json_digestable_form(transactions: List[Transaction]):
    l=[]
    for i in range(len(transactions)):
        tx_dict=transactions[i].to_dict()
        if(transactions[i].sender!="Genesis"):
            tx_dict["sign"]=base64.b64encode(transactions[i].sign).decode()
        l.append(tx_dict)
    return l


class BaseBlock:
    def __init__(self, prevHash:str, transactions:List[Transaction], ts=None, id=None):
        self.prevHash=prevHash
        self.transactions=transactions
        self.id=id or str(uuid.uuid4())
        self.ts=ts or int(datetime.now().timestamp() * 1000)
        self.files: Dict[str: str] = {}
    
    def transaction_exists_in_block(self, transaction: Transaction):
        for i in range(len(self.transactions)):
            if self.transactions[i]==transaction:
                return True
        return False

    def cid_exists_in_block(self, cid: str):
        for file_hash in list(self.files.keys()):
            if file_hash==cid:
                return True
        return False

class CommonChain:

    def __init__(self, genesis_block=None, block_list=None):

        if genesis_block is not None:
            self.chain = [genesis_block]
            print("Initializing Chain...")

        elif block_list is not None:
            self.chain = block_list.copy()

        else:
            raise ValueError("Invalid initialization")

    @property
    def lastBlock(self):
        return self.chain[-1]
    
    def to_block_dict_list(self):
        block_dict_list=[]
        for block in self.chain:
            block_dict_list.append(block.to_dict())
        
        return block_dict_list

    def transaction_exists_in_chain(self, transaction: Transaction):
        for block in reversed(self.chain):
            if block.transaction_exists_in_block(transaction):
                return True
        
        return False

    def cid_exists_in_chain(self, cid: str):
        for block in reversed(self.chain):
            if block.cid_exists_in_block(cid):
                return True
        
        return False        


class Wallet:
    def __init__(self, private_key_pem: str = None):
        if not private_key_pem:
            self.private_key = SigningKey.generate(curve=SECP256k1, hashfunc=SIGNATURE_HASH)
        else:
            self.private_key = SigningKey.from_pem(private_key_pem, hashfunc=SIGNATURE_HASH)
            
        self.private_key_pem = self.private_key.to_pem().decode()

        self.public_key = self.private_key.get_verifying_key()

        self.public_key_pem = self.public_key.to_pem().decode()

def transaction_exists_in_block_list(blockList, transaction_tc:Transaction, idx):
    """
        Return True when `transaction_tc` already appears in one of the
        blocks before index `idx`.

        This used to return False on a hit and None otherwise, so every
        caller - and they all test it as a boolean - saw "no duplicate"
        whatever happened, and a signed transaction could be replayed into
        as many blocks as an attacker liked. The loop also stopped one block
        short of the block being validated.
    """
    for i in range(min(idx, len(blockList))):
        currBlock=blockList[i]
        for transaction in currBlock.transactions:
            if(transaction.id==transaction_tc.id):
                # We sign the id of the transaction,
                # if it was truly a duplicate transaction
                # meant to reuse a sign then id must be the same
                # otherwise we'll get the invalid sign error
                return True
    return False
            
def valid_chain_length(i):
    valid_chain_len=i # because we use zero indexing
    # We must be careful in how we choose which blocks are valid, since a block that was valid in before a new block is added shouldn't then become of undecided nature
    # i.e for exapmple when length is 9 say the first 7 blocks are considered valid then when length becomes 10, it shouldn't become 5 or something like that
    # For larger chains of length greater than 250 we assume blocks of depth greater than 50 is valid
    if(valid_chain_len<250):
        valid_chain_len=valid_chain_len-(valid_chain_len//5)
    else:
        valid_chain_len-=50
    return valid_chain_len 