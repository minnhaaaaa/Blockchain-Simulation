import asyncio, websockets, traceback, hashlib
from websockets.exceptions import ConnectionClosed
import argparse, json, uuid, base64
import threading, socket, os, subprocess
from datetime import datetime, timedelta
from typing import Set, Dict, List, Tuple, Any
from consensus.pos.blockchain_structures import Transaction, Stake, Block, Wallet, Chain, isvalidChain, weight_of_chain
from consensus.pos import core, manifest as room_manifest
from consensus.pos.events import EventRejection, JobLedger, Authority
from shared_blockchain_structures import (
    verify_signature,
    remember_message_id,
    resolve_host,
    validate_port,
    MAX_KNOWN_PEERS,
)
from ipfs.ipfs import addToIpfs, download_ipfs_file_subprocess
from smart_contract.contracts_db import SmartContractDatabase
from smart_contract.secure_executor import SecureContractExecutor
from storage.storage_manager import save_key, load_key, save_chain, load_chain, save_peers, load_peers
from ecdsa import VerifyingKey, BadSignatureError
import tempfile, threading
from pathlib import Path
import ast
from canonical import signing_bytes

MAX_OUTPUT=2**256
GAS_PRICE = 0.001 # coin per gas unit
BASE_DEPLOY_COST = 5
CONSENSUS ="pos"

class VrfThresholdException(Exception):
    pass

def get_random_element(s):
    """
        Return a random element from a set
    """
    import random
    return random.choice(list(s)) if s else None

def normalize_endpoint(ep):
    """
        Return host resolved into ipv4 address and port converted into int datatype - maintains consistency in the code

        Host and port arrive from peer messages, so they are validated here;
        an out of range port or a host crafted to make us issue an unbounded
        blocking DNS lookup used to reach socket.gethostbyname unchecked.
    """
    host, port = ep
    return (resolve_host(host), validate_port(port))

def get_contract_code_from_notepad():
    # Create a temporary file with a .py extension
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode='w+', encoding='utf-8') as tmp_file:
        temp_filename = tmp_file.name
        tmp_file.write("# Write your smart contract function here.\n")
        tmp_file.write("def contract_logic(parameter1, parameter2, parameter3, state):\n")
        tmp_file.write("    # your code here\n")
        tmp_file.write("    return state, 'some message'\n")
    
    # Open it in Notepad (waits until closed)
    subprocess.call(["notepad.exe", temp_filename])

    # Read the edited code
    with open(temp_filename, 'r', encoding='utf-8') as f:
        contract_code = f.read()

    # Optional: remove the temp file
    os.remove(temp_filename)

    return contract_code

class Peer:
    def __init__(self, host, port, name, staker:bool, activate_disk_load, activate_disk_save,
                 manifest=None, storage=None, event_rules=None):
        """
            manifest    - verified signed room manifest; when given, the room's
                          genesis is derived from it and no other genesis is
                          ever accepted.
            storage     - NodeStorage namespaced by <data-root>/<room>/<node>;
                          when None the legacy global storage is used.
            event_rules - dict(max_clock_skew_ms, max_event_bytes[, authority])
                          enabling signed agent events. Without it a block that
                          carries events is invalid.
        """
        self.host = host
        self.name = name
        self.staker=staker

        self.storage = storage
        self.params = core.ConsensusParams.legacy()
        self.manifest = None
        self.genesis_hash = None
        self.room_id = None
        if manifest is not None:
            self.manifest = room_manifest.verify_manifest(manifest)
            self.genesis_hash = room_manifest.genesis_hash(self.manifest)
            self.room_id = self.manifest["room_id"]
            self.params = core.ConsensusParams.from_manifest(self.manifest)
            if storage is not None:
                storage.save_manifest(self.manifest)
        self.epoch_time = self.params.epoch_seconds
        self.event_rules = event_rules
        self.event_pool: List[dict] = []
        # Guards chain/ledger/pool for callers on other threads (Flask via NodeService).
        self.state_lock = threading.RLock()
        self.loop = None
        self.server = None
        self.ready = threading.Event()
        # Sockets that proved they belong to this room (room_hello matched the
        # manifest genesis) and the public key each presented.
        self.admitted = set()
        self.ws_public_keys = {}
        self._room_challenges = {}
        self._finalized_notified = set()
        self.included_events = {}
        self.ledger: JobLedger = self._new_ledger() if event_rules else None
        self.state_listeners = []

        self.activate_disk_save = activate_disk_save

        self.port = port
        self.ipfs_port = port + 50  # API port
        self.gateway_port = port + 81  # Gateway port
        self.swarm_tcp = port + 2
        self.swarm_udp = port + 3
        self.repo_path = Path.home() / f".ipfs_{port}"
        self.env = os.environ.copy()
        self.env["IPFS_PATH"] = str(self.repo_path)

        self.server_connections :Set[websockets.WebSocketServerProtocol]=set() # For inbound peers ie websockets that connect to us and treat us as the server
        self.client_connections :Set[websockets.WebSocketServerProtocol]=set() # For outbound peers ie websockets we initiated, we are the clients

        self.outbound_peers: Set[tuple]=set()
        # The peers to which we currently maintain a outbound connection

        self.seen_message_ids: Set[str]= set()
        # Used to remove duplicate messages, messages that return to us after a round of broadcasting

        self.name_to_public_key_dict: Dict[str, str]={}
        if activate_disk_load == "y":
            self.load_known_peers_from_disk()
        else:
            self.known_peers = None
        if not self.known_peers:
            self.known_peers : Dict[Tuple[str, int], Tuple[str, str]]={} # (host, port):(name, public key)
        """
            We store all the peers we know here, we compare this with outbound peers in dicover_peers
            to find to which nodes we have not yet made a connection
        """
        
        self.staked_amt:int=0
        self.got_pong: Dict[websockets.WebSocketServerProtocol, bool]={}
        """
            We set the value of each websocket in this dictionary false before sending ping
            If we get a pong from a particular websocekt we assign it True.
            We remove all websockets that don't send a pong in time. 
        """

        self.have_sent_peer_info: Dict[websockets.WebSocketServerProtocol, bool]={}
        """
            When we form an outbound connection, on receiving the first pong after our first ping
            we send them our peer_info, but we don't want to keep making the elaborate handshake
            so after the first time of getting pong we don't send them our peer info
            I'll explain the handshake in README.md
        """

        
        self.last_epoch_end_ts=datetime.now()
        self.mem_pool: List[Transaction]=list()
        self.mem_pool_lock=asyncio.Lock() 
        
        self.file_hashes: Dict[str, str]={}
        self.file_hashes_lock=asyncio.Lock()
        self.daemon_process=None

        self.current_stakes: set[Stake]=set() # Public key is stored as pem string
        self.current_stakers:Dict[str, int]={}
        self.curr_stakers_condition=asyncio.Condition() 
        self.reset_stake_snapshot()
        
        
        if activate_disk_load == "y":
            self.load_key_from_disk()
        else:
            self.wallet = None
        if not self.wallet:
            self.wallet=Wallet()
            if self.activate_disk_save == "y":
                self.save_key_to_disk()
        
        if activate_disk_load == "y":
            self.load_chain_from_disk() # If no chain data stored, self.chain will be assigned to None
        else:
            self.chain = None

        self.contractsDB = SmartContractDatabase()

        self.create_block_condition=asyncio.Condition()
        """
            Starts a timer for the creation of next block
        """
        self.mine_task=None

    def _new_ledger(self):
        if not self.event_rules or not self.room_id:
            raise ValueError("event rules need a room manifest")
        return JobLedger(
            self.room_id,
            self.event_rules["max_clock_skew_ms"],
            self.event_rules["max_event_bytes"],
            self.event_rules.get("authority"),
        )

    def rebuild_ledger(self):
        """Recompute the committed event ledger from the chain and drop pool events it invalidates."""
        if not self.event_rules:
            return
        with self.state_lock:
            old_included = dict(self.included_events)
            ledger = self._new_ledger()
            new_included = {}
            for block in self.chain.chain:
                for event in block.events:
                    ledger.check_and_apply(event)
                    new_included[event["event_id"]] = event
            # Events that were in blocks of a chain we just abandoned go back
            # to the pool if they are still valid, otherwise they are rejected.
            orphaned = [e for i, e in old_included.items() if i not in new_included]
            pooled_ids = {e["event_id"] for e in self.event_pool}
            self.ledger = ledger
            self.included_events = new_included
            self.event_pool = self._revalidate_pool(self.event_pool + [e for e in orphaned if e["event_id"] not in pooled_ids])
            for event in orphaned:
                if any(e["event_id"] == event["event_id"] for e in self.event_pool):
                    self.notify_state_change({"event_id": event["event_id"], "job_id": event["job_id"], "ledger_state": "submitted"})
            for event_id, event in new_included.items():
                if event_id not in old_included:
                    self.notify_state_change({"event_id": event_id, "job_id": event["job_id"], "ledger_state": "included"})
            self.notify_finality()

    def _revalidate_pool(self, pool):
        """Keep pool events that are still valid; announce the rest as rejected."""
        working = self.ledger.clone()
        kept = []
        for event in pool:
            try:
                working.check_and_apply(event)
                kept.append(event)
            except EventRejection:
                self.notify_state_change({"event_id": event["event_id"], "job_id": event["job_id"], "ledger_state": "rejected"})
        return kept

    def notify_finality(self):
        """Announce every event that has just become at least finality_depth blocks deep."""
        if not self.event_rules:
            return
        head = len(self.chain.chain) - 1
        depth = self.params.finality_depth
        for height in range(0, max(0, head - depth) + 1):
            for event in self.chain.chain[height].events:
                if event["event_id"] not in self._finalized_notified:
                    self._finalized_notified.add(event["event_id"])
                    self.notify_state_change({"event_id": event["event_id"], "job_id": event["job_id"], "ledger_state": "finalized"})

    def notify_state_change(self, change: dict):
        for listener in list(self.state_listeners):
            try:
                listener(change)
            except Exception as e:
                print(f"state listener failed: {e}")

    def save_key_to_disk(self):
        key = self.wallet.private_key_pem
        if self.storage:
            return self.storage.save_key(key)
        save_key(key, CONSENSUS)

    def load_key_from_disk(self):
        key = self.storage.load_key() if self.storage else load_key(CONSENSUS)
        if not key:
            self.wallet = None
            return
        self.wallet = Wallet(key)

    def load_chain_from_disk(self):
        block_dict_list = self.storage.load_chain() if self.storage else load_chain(CONSENSUS)
        if not block_dict_list:
            self.chain = None
            return
        block_list: List[Block]=[]

        for block_dict in block_dict_list:
            block=self.block_dict_to_block(block_dict)
            block_list.append(block)

        # Persisted state is re-validated exactly like a chain received from
        # a peer: a tampered file must not become the local chain.
        if not isvalidChain(block_list, self.genesis_hash, self._new_ledger if self.event_rules else None, self.params):
            raise ValueError("stored chain failed validation; refusing to start from it")
        self.chain=Chain(blockList=block_list)
        self.chain.params=self.params
        if self.storage:
            self.apply_evidence_records(self.storage.load_evidence())
        if self.event_rules:
            self.rebuild_ledger()

    def save_chain_to_disk(self):
        chain = self.chain.to_block_dict_list()
        if self.storage:
            self.storage.save_chain(chain)
            return self.storage.save_evidence(self.chain.evidence_records)
        save_chain(chain, CONSENSUS)

    def save_known_peers_to_disk(self):
        content = {}
        for key, value in self.known_peers.items():
            content[json.dumps(key)] = list(value)
        if self.storage:
            return self.storage.save_peers(content)
        save_peers(content, CONSENSUS)

    def load_known_peers_from_disk(self):
        content = self.storage.load_peers() if self.storage else load_peers(CONSENSUS)
        if not content:
            self.known_peers = None
            return
        self.known_peers = {}
        for key, value in content.items():
            self.known_peers[tuple(ast.literal_eval(key))] = tuple(value)
        for key, value in self.known_peers.items():
            self.name_to_public_key_dict[value[0].lower()] = value[1]

    async def send_peer_info(self, websocket):
        """
            Function made to send the peer (self) info
        """
        pkt={
            "type":"peer_info",
            "id":str(uuid.uuid4()),
            "data":{
                "host":self.host,
                "port":self.port,
                "name":self.name,
                "public_key":self.wallet.public_key_pem
                }
        }

        remember_message_id(self.seen_message_ids, pkt["id"])
        await websocket.send(json.dumps(pkt))

    async def send_known_peers(self, websocket):
        """
            Function for sending known_peers
            (information regarding all the peers we know)
        """
        peers=[{"host":h, "port":p, "name":n, "public_key":s}
               for (h, p), (n,s) in self.known_peers.items()]
        peers.append({"host":self.host, "port":self.port, "name":self.name, "public_key":self.wallet.public_key_pem})
        pkt={
            "type":"known_peers",
            "id":str(uuid.uuid4()),
            "peers":peers
        }
        remember_message_id(self.seen_message_ids, pkt["id"])
        await websocket.send(json.dumps(pkt))

    def block_dict_to_block(self, block_dict:Dict[str, Any]):    
        """
            Verified whether given information in block_dict is valid and
            creates a block out of the information or returns None
            We sent a receive blocks as a dictionary
            block["trasnsactions"] is a list of dictionaries that
            represent transactions
        """

        new_block_id=block_dict.get("id")
        new_block_prevHash=block_dict.get("prevHash")
        new_block_ts=block_dict.get("ts")

        transactions=[]
        for transaction_dict in block_dict["transactions"]:
            transaction=Transaction(transaction_dict["payload"], transaction_dict["sender"], transaction_dict["receiver"], transaction_dict["id"], transaction_dict["ts"])
            if(transaction.sender!="Genesis"):
                transaction.sign=base64.b64decode(transaction_dict["sign"])
            transactions.append(transaction)
        
        has_events=bool(block_dict.get("events"))
        if(not(new_block_id and new_block_ts and (transactions or has_events))): # Genesis block doesn't have prevHash, it's an empty string
            return None
        
        newBlock=Block(new_block_prevHash, transactions, new_block_ts, new_block_id)   
        staked_amt=block_dict.get("staked_amt")
        if(staked_amt):
            newBlock.staked_amt=staked_amt

        if(block_dict.get("files")):
            newBlock.files=block_dict["files"]

        block_events=block_dict.get("events") or []
        if isinstance(block_events, list) and all(isinstance(e, dict) for e in block_events):
            newBlock.events=block_events

        creator=block_dict.get("creator")
        if(creator):
            newBlock.creator=creator

        sign_b64=block_dict.get("sign")

        if(sign_b64):
            newBlock.sign=base64.b64decode(sign_b64)

        stakers_list:List[Stake]=[]
        for staker_dict in block_dict.get("stakers") or []:
            new_Stake=self.stake_dict_to_stake(staker_dict)
            if(not new_Stake):
                continue
            stakers_list.append(new_Stake)
        
        vrf_proof=block_dict.get("vrf_proof_b64")
        seed=block_dict.get("seed")
        if(vrf_proof and seed):
            newBlock.vrf_proof=base64.b64decode(vrf_proof)
            newBlock.seed=seed

        newBlock.stakers=stakers_list
        return newBlock
    
    def stake_dict_to_stake(self, stake_dict:Dict[str, Any]):    
        """
            This function creates a stake out of the information
            stored inside stake_dict
        """
        id=stake_dict.get("id")
        staker=stake_dict.get("staker")
        amt=stake_dict.get("amt")
        ts=stake_dict.get("ts")
        sign=stake_dict.get("sign")

        if(not(id and staker and amt)):
            return None
        if not sign and not (self.manifest and self.validator_stakes.get(staker) == amt):
            return None
        
        stake=Stake(staker, amt, ts)
        stake.id=id

        stake.sign=base64.b64decode(sign, validate=True) if sign else None
        return stake

    @property
    def validator_stakes(self):
        if self.manifest:
            return {a["public_key"]: a["stake"] for a in self.manifest["genesis"]["allocations"] if a["stake"]}
        return {}

    def reset_stake_snapshot(self):
        """Room consensus uses the immutable genesis registry, never gossip state."""
        self.current_stakers = self.validator_stakes
        self.current_stakes = set()
        if self.manifest:
            for public_key, amount in sorted(self.current_stakers.items()):
                stake = Stake(public_key, amount, self.manifest["genesis"]["created_at_ms"])
                stake.id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                    f"agentguard:stake:{self.manifest['genesis']['block_id']}:{public_key}"))
                self.current_stakes.add(stake)

    def valid_deploy_transaction(self, payload):
        contract_code = payload[0]
        gas_used = len(contract_code)//10 + BASE_DEPLOY_COST
        amount = gas_used * GAS_PRICE
        if amount != payload[-1]:
            return False
        return True

    def valid_invoke_transaction(self, payload):
        contract_id = payload[0]
        func_name = payload[1]
        args = payload[2]
        response = self.run_contract([contract_id, func_name, args])
        if(response["error"] != None):
            return False
        state = response["state"]
        gas_used = response["gas_used"]
        amount = gas_used * GAS_PRICE
        if state != payload[3]:
            return False
        if amount != payload[-1]:
            return False
        return True

    def get_unique_name(self, base_name):
        existing_names = []
        for key, value in self.known_peers.items():
            existing_names.append(value[0].lower())

        existing_names.append(self.name)
        
        base_name = base_name.lower()
        if base_name not in existing_names:
            return base_name
        
        counter = 1
        while True:
            new_name = f"{base_name}{counter}"
            if new_name not in existing_names:
                return new_name
            counter += 1

    async def send_room_hello(self, websocket):
        """Challenge the peer to prove possession of its room signing key."""
        if not self.manifest:
            return
        challenge = uuid.uuid4().hex
        self._room_challenges[websocket] = challenge
        pkt = {"type": "room_challenge", "id": str(uuid.uuid4()), "challenge": challenge}
        remember_message_id(self.seen_message_ids, pkt["id"])
        await websocket.send(json.dumps(pkt))

    async def disconnect_all(self):
        """Close every connection (used when leaving a room)."""
        for ws in list(self.server_connections | self.client_connections):
            try:
                await ws.close()
            except Exception:
                pass
        self.server_connections.clear()
        self.client_connections.clear()
        self.outbound_peers.clear()
        self.admitted.clear()
        self._room_challenges.clear()
        self.ws_public_keys.clear()

    async def handle_messages(self, websocket, msg):
        """
            This is a function to handle messages as the name suggests
            It faciliates the handshake between client and server. 
            It also accepts transactions, blocks and chains in the format
            in which we send them. Then this function recreates these and
            performs the necessary operations
        """
        # Read the handshake protocol within readme to understand the flow of messages

        t = msg.get("type")
        id = msg.get("id")
        # Every message has a type and an id

        if not t or not id:
            return

        # A signed response to this connection's unique challenge binds the
        # socket to a key, room, and immutable genesis. A copied hello cannot
        # be replayed on another connection.
        if self.manifest and websocket is not None:
            if t == "room_challenge" and websocket not in self.admitted:
                challenge = msg.get("challenge")
                if not isinstance(challenge, str) or len(challenge) != 32:
                    await websocket.close()
                    return
                response = {"room_id": self.room_id, "genesis_hash": self.genesis_hash,
                            "public_key": self.wallet.public_key_pem, "challenge": challenge}
                response["signature"] = base64.b64encode(self.wallet.private_key.sign(
                    signing_bytes("agentguard.room-hello.v1", response))).decode("ascii")
                await websocket.send(json.dumps({"type": "room_hello", "id": str(uuid.uuid4()), **response}))
                return
            if t == "room_hello":
                challenge = self._room_challenges.pop(websocket, None)
                hello = {field: msg.get(field) for field in ("room_id", "genesis_hash", "public_key", "challenge")}
                try:
                    signature = base64.b64decode(msg.get("signature", ""), validate=True)
                    signed = verify_signature(hello["public_key"], signature,
                                              signing_bytes("agentguard.room-hello.v1", hello))
                except (ValueError, TypeError, KeyError):
                    signed = False
                if msg.get("room_id") != self.room_id or msg.get("genesis_hash") != self.genesis_hash \
                        or not isinstance(msg.get("public_key"), str) or challenge != msg.get("challenge") or not signed:
                    print("\nPeer belongs to a different room or genesis; disconnecting\n")
                    await websocket.close()
                    return
                self.admitted.add(websocket)
                self.ws_public_keys[websocket] = msg["public_key"]
                await websocket.send(json.dumps({"type": "ping", "id": str(uuid.uuid4())}))
                return
            if websocket not in self.admitted:
                return

        if id in self.seen_message_ids:
            return
        
        remember_message_id(self.seen_message_ids, id)

        if t == "ping":
            # print("Received Ping")
            pkt = {
                "type": "pong",
                "id": str(uuid.uuid4())
            }
            remember_message_id(self.seen_message_ids, pkt["id"])
            await websocket.send(json.dumps(pkt))

        elif t == "pong":
            self.got_pong[websocket] = True
            if not self.have_sent_peer_info.get(websocket, True):
                await self.send_peer_info(websocket)
                self.have_sent_peer_info[websocket] = True

        elif t == 'peer_info':
            data = msg.get("data")
            if not data:
                return
            if self.manifest and websocket is not None and data.get("public_key") != self.ws_public_keys.get(websocket):
                await websocket.close()
                return
            
            if not all(k in data for k in ['host', 'port', 'name', 'public_key']):
                return
            
            normalized_self = normalize_endpoint((self.host, self.port))
            normalized_endpoint = normalize_endpoint((data['host'], data['port']))
            if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                if len(self.known_peers) >= MAX_KNOWN_PEERS:
                    return
                self.known_peers[normalized_endpoint] = (data['name'], data['public_key'])
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
                self.name_to_public_key_dict[data['name'].lower()] = data['public_key']
                print(f"Registered peer {data['name']} {data['host']}:{data['port']}")
                await self.send_known_peers(websocket)

        elif t == "add_peer":
            data = msg.get("data")
            if not data:
                return
            
            if not all(k in data for k in ['host', 'port', 'name', 'public_key']):
                return
            
            normalized_self = normalize_endpoint((self.host, self.port))
            normalized_endpoint = normalize_endpoint((data["host"], data["port"]))
            new_peer_msg_id = str(uuid.uuid4())
            if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                proposed_name = self.get_unique_name(data["name"])
                if proposed_name != data["name"]:
                    pkt = {
                        "type": "change_name",
                        "id": str(uuid.uuid4()),
                        "new_peer_msg_id": new_peer_msg_id,
                        "new_name": proposed_name
                    }
                    await websocket.send(json.dumps(pkt))
                    data["name"] = proposed_name
                if len(self.known_peers) >= MAX_KNOWN_PEERS:
                    return
                self.known_peers[normalized_endpoint] = (data["name"], data["public_key"])
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
                self.name_to_public_key_dict[data["name"].lower()] = data["public_key"]
                print(f"Registered peer {data["name"]} {data["host"]}:{data["port"]}")
                await self.send_known_peers(websocket)
                pkt = {
                    "type": "new_peer",
                    "id": new_peer_msg_id,
                    "data": {
                        "host": data["host"],
                        "port": data["port"],
                        "name": data["name"],
                        "public_key": data["public_key"]
                    }
                }
                remember_message_id(self.seen_message_ids, pkt["id"])
                await self.broadcast_message(pkt)

        elif t == "new_peer":
            data = msg.get("data")
            if not data:
                return
            
            if not all(k in data for k in ['host', 'port', 'name', 'public_key']):
                return
            
            normalized_self = normalize_endpoint((self.host, self.port))
            normalized_endpoint = normalize_endpoint((data["host"], data["port"]))
            if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                if len(self.known_peers) >= MAX_KNOWN_PEERS:
                    return
                self.known_peers[normalized_endpoint] = (data["name"], data["public_key"])
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
                self.name_to_public_key_dict[data["name"].lower()] = data["public_key"]
                print(f"Registered peer {data["name"]} {data["host"]}:{data["port"]}")
                await self.broadcast_message(msg)

        elif t == "change_name":
            new_name = msg.get("new_name")
            new_peer_msg_id = msg.get("new_peer_msg_id")
            if not new_name or not new_peer_msg_id:
                return
            
            self.name = new_name
            remember_message_id(self.seen_message_ids, new_peer_msg_id)

        elif t == "known_peers":
            peers = msg.get("peers")
            if not peers:
                return
            
            new_peer_found = False
            for peer in peers:
                if not all(k in peer for k in ['host', 'port', 'name', 'public_key']):
                    continue
                
                normalized_self = normalize_endpoint((self.host, self.port))
                normalized_endpoint = normalize_endpoint((peer['host'], peer['port']))
                if normalized_endpoint not in self.known_peers and normalized_endpoint != normalized_self:
                    if len(self.known_peers) >= MAX_KNOWN_PEERS:
                        break
                    print(f"Discovered peer {peer['name']} at {peer['host']}:{peer['port']}")
                    new_peer_found = True
                    self.known_peers[normalized_endpoint] = (peer['name'], peer['public_key'])
                    self.name_to_public_key_dict[peer['name'].lower()] = peer['public_key']
            if new_peer_found:
                if self.activate_disk_save == "y":
                    self.save_known_peers_to_disk()
            pkt = {
                "type": "chain_request",
                "id": str(uuid.uuid4())
            }
            await websocket.send(json.dumps(pkt))

        elif t == "file":
            cid = msg.get("cid")
            desc = msg.get("desc")
            if not cid or not desc:
                return
            
            async with self.file_hashes_lock:
                self.file_hashes[cid] = desc

            await self.broadcast_message(msg)

        elif t == "new_tx":
            tx_str = msg.get("transaction")
            sender_pem = msg.get("sender_pem")
            sign = msg.get("sign")
            
            if not tx_str or not sender_pem or not sign:
                return
            
            try:
                tx = json.loads(tx_str)
            except json.JSONDecodeError:
                return
            
            if not all(k in tx for k in ['payload', 'sender', 'receiver', 'id', 'ts']):
                return
            
            amount = 0
            if tx['receiver'] == "deploy" or tx['receiver'] == "invoke":
                if not isinstance(tx['payload'], list) or len(tx['payload']) == 0:
                    return
                amount = tx['payload'][-1]
            else:
                amount = tx['payload']
            
            if amount <= 0:
                print("\nInvalid Transaction, amount<=0\n")
                return
            
            transaction = Transaction(tx['payload'], tx['sender'], tx['receiver'], tx['id'], tx['ts'])
            if self.chain.transaction_exists_in_chain(transaction):
                print(f"{self.name} Transaction already exists in chain")
                return
            
            try:
                sign_bytes = base64.b64decode(sign)
            except Exception:
                print("Invalid signature encoding")
                return

            if transaction.receiver == "deploy":
                if not self.valid_deploy_transaction(transaction.payload):
                    return
            if transaction.receiver == "invoke":
                if not self.valid_invoke_transaction(transaction.payload):
                    return
                
            if amount > self.chain.calc_balance(transaction.sender, self.mem_pool, list(self.current_stakes)):
                print("\nAttempt to spend more than one has, Invalid transaction\n")
                return

            # The signature was checked against `sender_pem`, a field sitting
            # beside the transaction in the message rather than the `sender`
            # named inside it. An attacker could put a victim's public key in
            # the transaction, sign the whole thing with their own key, send
            # their own key as sender_pem, and have the transaction accepted
            # and relayed as if the victim had spent their coins.
            if str(transaction)!=tx_str:
                print("Transaction does not match its signed form")
                return

            if not verify_signature(transaction.sender, sign_bytes, tx_str):
                print("Invalid Signature")
                return
            
            transaction.sign = sign_bytes
            
            print("\nValid Transaction")
            print(f"\n{msg['type']}: {msg['transaction']}")
            print("\n")

            async with self.mem_pool_lock:
                self.mem_pool.append(transaction)
            await self.broadcast_message(msg)

        elif t == "stake_announcement":
            if self.manifest:
                # Reserved stakes are authenticated by the room trust anchor.
                # An announcement cannot reweight or replace that registry.
                return
            stake_dict = msg.get("stake")
            if not stake_dict:
                return
            
            if not all(k in stake_dict for k in ["staker", "amt", "ts", "id", "sign"]):
                return
            
            stake = Stake(stake_dict["staker"], stake_dict["amt"], stake_dict["ts"])
            stake.id = stake_dict.get("id")

            pid = stake.staker
            amt = stake.amt

            if pid and amt:
                if amt <= 0:
                    return
                
                try:
                    sign = base64.b64decode(stake_dict["sign"])
                except Exception:
                    print("\nInvalid signature encoding\n")
                    return

                if not verify_signature(pid, sign, str(stake)):
                    print("\nWrong signature\n")
                    return

                stake.sign = sign

                # One staker announcing repeatedly under fresh ids used to add
                # an entry per announcement to current_stakes, inflating the
                # epoch's total stake and our memory along with it.
                if pid in self.current_stakers:
                    print("\nStaker already staked this epoch\n")
                    return

                if stake.amt > self.chain.calc_balance(stake.staker, self.mem_pool, list(self.current_stakes)):
                    print("\nInvalid stake, staked more than available\n")
                    return

                async with self.curr_stakers_condition:
                    self.current_stakes.add(stake)
                    self.current_stakers[pid] = int(amt)
                    print(f"New stake : {pid}:{amt}")
                await self.broadcast_message(msg)

        elif t == "new_block":
            new_block_dict = msg.get("block")
            vrf_proof_str = msg.get("vrf_proof")
            sign_str = msg.get("sign")
            
            if not new_block_dict or not vrf_proof_str or not sign_str:
                return
            
            if "creator" not in new_block_dict:
                return
            
            newBlock = self.block_dict_to_block(new_block_dict)
            if newBlock is None:
                return

            if not self.chain.isValidBlock(newBlock, self.ledger):
                print("\nInvalid Block\n")
                return
            
            try:
                # Convert Unix timestamp to datetime
                if isinstance(newBlock.ts, (int, float)):
                    block_time = datetime.fromtimestamp((newBlock.ts)/1000)
                elif isinstance(newBlock.ts, str):
                    block_time = datetime.fromisoformat(newBlock.ts)
                elif isinstance(newBlock.ts, datetime):
                    block_time = newBlock.ts
                else:
                    print("\nInvalid Block (unknown timestamp format)\n")
                    return

                current_time = datetime.now()

                # Check block isn't from the future (with tolerance for clock skew)
                if block_time > current_time + timedelta(milliseconds=self.params.max_clock_skew_ms):
                    print("\nInvalid Block (timestamp in future)\n")
                    return

                # Check block isn't too old
                if block_time < current_time - timedelta(seconds=self.epoch_time * 2):
                    print("\nInvalid Block (timestamp too old)\n")
                    return

                # Verify minimum time since last block
                if len(self.chain.chain) > 0:
                    last_block_ts = self.chain.lastBlock.ts
                    # Handle the same types for lastBlock timestamp
                    if isinstance(last_block_ts, (int, float)):
                        last_block_time = datetime.fromtimestamp(last_block_ts/1000)
                    elif isinstance(last_block_ts, str):
                        last_block_time = datetime.fromisoformat(last_block_ts)
                    elif isinstance(last_block_ts, datetime):
                        last_block_time = last_block_ts
                    else:
                        print("\nInvalid Block (cannot validate timing against last block)\n")
                        return
                        
                    time_diff = (block_time - last_block_time).total_seconds()
                    
                    # Blocks shouldn't come faster than the staking registration period
                    if time_diff < self.epoch_time * 5/6:
                        print(f"\nInvalid Block (created too quickly: {time_diff}s < {self.epoch_time * 5/6}s)\n")
                        return
            except (ValueError, AttributeError, TypeError, OSError) as e:
                print(f"\nInvalid Block (bad timestamp format): {e}\n")
                return
            
            try:
                vrf_proof = base64.b64decode(vrf_proof_str)
                sign = base64.b64decode(sign_str)
            except Exception as e:
                print(f"\nInvalid Block (encoding error): {e}\n")
                return

            creator_pem = new_block_dict["creator"]
            print(f"\n{new_block_dict}\n")
            try:
                epoch_seed = self.chain.epoch_seed()
                if not core.vrf_verify_proof(creator_pem, vrf_proof, epoch_seed):
                    print("\nInvalid Block (VRF_PROOF Signature Error)\n")
                    return

                if not verify_signature(creator_pem, sign, str(newBlock)):
                    print("\nInvalid Block (Block Signature Error)\n")
                    return
                
                if newBlock.seed != epoch_seed:
                    print("\nSeed May Have Been Altered\n")
                    return

                if newBlock.vrf_proof != vrf_proof:
                    print("\nInvalid Block (proof in packet differs from the signed proof)\n")
                    return

                creator_key = new_block_dict["creator"]
                if creator_key not in self.current_stakers:
                    print("\nInvalid Block (creator not in current stakers)\n")
                    return

                # The block must carry exactly the epoch snapshot this node
                # authenticated - omitting or adding a staker changes the
                # creator's odds, so anything short of equality is rejected.
                if not core.snapshot_matches(newBlock.stakers, self.current_stakers):
                    print("\nInvalid Block (stake snapshot differs from the authenticated epoch snapshot)\n")
                    return

                try:
                    total_amt_staked = core.validate_stake_snapshot(newBlock.stakers, creator_key, self.current_stakers[creator_key], self.params.minimum_stake,
                                                                   authenticated=self.validator_stakes if self.manifest else None)
                except core.ConsensusError as e:
                    print(f"\nInvalid Block ({e})\n")
                    return

                if newBlock.staked_amt != self.current_stakers[creator_key]:
                    print("\nInvalid Block (declared stake does not match the announced stake)\n")
                    return

                vrf_output_int = core.vrf_output_int(creator_key, epoch_seed)
                if not core.is_eligible(vrf_output_int, newBlock.staked_amt, total_amt_staked):
                    raise VrfThresholdException("VRF output is not strictly below the threshold")
                newBlock.sign = sign

            except VrfThresholdException as e:
                print(f"\nInvalid Block (VRF_OUTPUT>=THRESHOLD), {e}\n")
                return
            
                
            for transaction in newBlock.transactions:
                if transaction.receiver == "invoke":
                    if not self.valid_invoke_transaction(transaction.payload):
                        return
                if transaction.receiver == "deploy":
                    if not self.valid_deploy_transaction(transaction.payload):
                        return

            newBlock.creator = new_block_dict["creator"]
            with self.state_lock:
                self.chain.chain.append(newBlock)
                self.commit_block_events(newBlock)
            print("\n\n Block Appended \n\n")
            self.last_epoch_end_ts = datetime.now()

            for transaction in newBlock.transactions:
                if transaction.receiver == "deploy":
                    self.deploy_contract(transaction)

            async with self.mem_pool_lock:
                for transaction in self.mem_pool:
                    if newBlock.transaction_exists_in_block(transaction):
                        self.mem_pool.remove(transaction)
            
            async with self.file_hashes_lock:
                for hash in list(self.file_hashes.keys()):
                    if newBlock.cid_exists_in_block(hash):
                        self.file_hashes.pop(hash, None)
            
            self.staked_amt = 0
            async with self.curr_stakers_condition:
                self.reset_stake_snapshot()

            await self.broadcast_message(msg)
            if self.activate_disk_save == "y":
                self.save_chain_to_disk()

        elif t == "slash_announcement":
            block1_dict = msg.get("evidence1")
            block1_sign = msg.get("block1_sign")
            block2_dict = msg.get("evidence2")
            block2_sign = msg.get("block2_sign")
            pos = msg.get("pos")
            
            if not all([block1_dict, block1_sign, block2_dict, block2_sign, pos is not None]):
                return
            
            if not isinstance(pos, int) or isinstance(pos, bool):
                return

            block1 = self.block_dict_to_block(block1_dict)
            if not block1 or not getattr(block1, 'creator', None):
                return
            try:
                block1.sign = base64.b64decode(block1_sign)
            except Exception:
                return

            block2 = self.block_dict_to_block(block2_dict)
            if not block2:
                return
            try:
                block2.sign = base64.b64decode(block2_sign)
            except Exception:
                return

            if pos < 0 or pos >= len(self.chain.chain):
                return

            try:
                applied = self.chain.apply_double_sign_evidence(block1, block2, pos)
            except core.ConsensusError as e:
                print(f"\nInvalid Slashing Evidence: {e}\n")
                return
            if applied:
                print(f"\nBlock {pos} slashed\n")
                if self.activate_disk_save == "y":
                    self.save_chain_to_disk()
                await self.broadcast_message(msg)
            # Already-applied evidence is ignored, so a penalty lands once.

        elif t == "agent_event":
            event = msg.get("event")
            if not isinstance(event, dict) or not self.event_rules:
                return
            try:
                self.accept_event(event, int(datetime.now().timestamp() * 1000))
            except EventRejection as e:
                print(f"\nRejected gossiped event: {e}\n")
                return
            await self.broadcast_message(msg)

        elif t == "chain_request":
            if not self.chain:
                return

            pkt = {
                "type": "chain",
                "id": str(uuid.uuid4()),
                "chain": self.chain.to_block_dict_list(),
                "evidence": self.chain.evidence_records,
            }
            await websocket.send(json.dumps(pkt))

        elif t == "chain":
            print("Received a Chain")
            block_dict_list = msg.get("chain")
            if not block_dict_list:
                return
            
            block_list = []

            for block_dict in block_dict_list:
                block = self.block_dict_to_block(block_dict)
                block_list.append(block)

            if not isvalidChain(block_list, self.genesis_hash, self._new_ledger if self.event_rules else None, self.params):
                print("\nInvalid Chain\n")
                return
            evidence = msg.get("evidence", [])
            if not isinstance(evidence, list):
                return

            # A chain rooted at a genesis block other than ours is a different
            # network, and its genesis allocates the starting coins.
            if self.chain and self.chain.chain and self.chain.chain[0].hash!=block_list[0].hash:
                print("\nChain has a different genesis block\n")
                return

            # If chain doesn't already exist we assign this as the chain
            if not self.chain:
                self.chain = Chain(blockList=block_list)
                self.chain.params = self.params
                self.rebuild_ledger()
                if self.activate_disk_save == "y":
                    self.save_chain_to_disk()
                
            else:
                pos = self.chain.checkEquivalence(block_list)
                if pos > 0 and self.chain.chain[pos].creator == block_list[pos].creator \
                        and self.chain.chain[pos].seed == block_list[pos].seed:
                    # Same creator, same height, same epoch seed, different
                    # signed blocks: this is double signing, not a fork.
                    await self.verify_and_slash(self.chain.chain[pos], block_list[pos], pos, block_list)
                elif self.chain.rewrite(block_list):
                    print("\nCurrent chain replaced by better-scoring chain\n")
                    self.rebuild_ledger()
                    if self.activate_disk_save == "y":
                        self.save_chain_to_disk()
                else:
                    print("\nCurrent chain scores at least as well as the received chain\n")

            self.apply_evidence_records(evidence)

            async with self.mem_pool_lock:
                for transaction in self.mem_pool:
                    if self.chain.transaction_exists_in_chain(transaction):
                        self.mem_pool.remove(transaction)
            
            async with self.file_hashes_lock:
                for hash in list(self.file_hashes.keys()):
                    if self.chain.cid_exists_in_chain(hash):
                        self.file_hashes.pop(hash, None)

    def commit_block_events(self, block: Block):
        """Fold an accepted block's events into the committed ledger and prune the pool."""
        self.notify_state_change({"kind": "block.appended", "hash": block.hash, "height": len(self.chain.chain) - 1})
        if not self.event_rules:
            return
        with self.state_lock:
            for event in block.events:
                self.ledger.apply(event)
                self.included_events[event["event_id"]] = event
                self.notify_state_change({"event_id": event["event_id"], "job_id": event["job_id"], "ledger_state": "included"})
            included = {e["event_id"] for e in block.events}
            self.event_pool = self._revalidate_pool([e for e in self.event_pool if e["event_id"] not in included])
            self.notify_finality()

    def apply_evidence_records(self, records):
        """Replay signed evidence; a forged witness cannot change balances."""
        if not self.chain:
            return
        for record in records:
            try:
                if not isinstance(record, dict) or len(record["blocks"]) != 2:
                    continue
                height=record["height"]
                if not isinstance(height,int) or isinstance(height,bool):
                    continue
                blocks=[self.block_dict_to_block(item) for item in record["blocks"]]
                if any(block is None or block.sign is None for block in blocks):
                    continue
                applied=self.chain.apply_double_sign_evidence(blocks[0],blocks[1],height)
                if applied and self.activate_disk_save == "y":
                    self.save_chain_to_disk()
            except (KeyError, TypeError, ValueError, core.ConsensusError):
                continue

    def pooled_ledger(self):
        """Committed state plus pending pool events (the 'submitted' view)."""
        working = self.ledger.clone()
        for event in self.event_pool:
            working.check_and_apply(event)
        return working

    def accept_event(self, event: dict, now_ms: int):
        """
            Fully validate a signed event against committed + pending state and
            queue it. Raises EventRejection; an invalid event never enters the pool.
        """
        if not self.event_rules:
            raise EventRejection("NODE_UNAVAILABLE", "this node has no event rules configured")
        if self.chain is None:
            raise EventRejection("NODE_UNAVAILABLE", "node has no chain yet")
        with self.state_lock:
            working = self.pooled_ledger()
            working.check(event, now_ms)
            self.event_pool.append(event)
        self.notify_state_change({"event_id": event["event_id"], "job_id": event["job_id"], "ledger_state": "submitted"})

    def schedule_event_gossip(self, event: dict):
        """Broadcast an accepted event from any thread once the network loop is running."""
        if self.loop is None:
            return
        pkt = {"type": "agent_event", "id": str(uuid.uuid4()), "event": event}
        remember_message_id(self.seen_message_ids, pkt["id"])
        asyncio.run_coroutine_threadsafe(self.broadcast_message(pkt), self.loop)

    def register_stake(self, amt: int):
        """Synchronous stake registration for the current epoch (no broadcast)."""
        if not isinstance(amt, int) or isinstance(amt, bool) or amt < self.params.minimum_stake:
            raise ValueError("stake must be an integer meeting minimum_stake")
        if self.manifest:
            if self.validator_stakes.get(self.wallet.public_key_pem) != amt:
                raise ValueError("stake must equal this validator's genesis reservation")
            self.reset_stake_snapshot()
            self.staked_amt = amt
            return next(s for s in self.current_stakes if s.staker == self.wallet.public_key_pem)
        if amt > self.chain.calc_balance(self.wallet.public_key_pem, self.mem_pool):
            raise ValueError("stake exceeds available balance")
        if self.wallet.public_key_pem in self.current_stakers:
            raise ValueError("validator is already registered")
        stake = Stake(self.wallet.public_key_pem, amt)
        stake.sign = self.wallet.private_key.sign(str(stake).encode())
        self.current_stakers[self.wallet.public_key_pem] = amt
        self.current_stakes.add(stake)
        self.staked_amt = amt
        return stake

    async def verify_and_slash(self, block1:Block, block2:Block, pos:int, block_list:List[Block]):
        try:
            applied = self.chain.apply_double_sign_evidence(block1, block2, pos)
        except core.ConsensusError as e:
            print(f"\nDouble-sign evidence rejected: {e}\n")
            return
        if not applied:
            return

        if self.activate_disk_save == "y":
            self.save_chain_to_disk()

        pkt={
            "type":"slash_announcement",
            "id":str(uuid.uuid4()),
            "evidence1":block1.to_dict(),
            "evidence2":block2.to_dict(),
            "block1_sign":base64.b64encode(block1.sign).decode(),
            "block2_sign":base64.b64encode(block2.sign).decode(),
            "pos":pos
        }
        await self.broadcast_message(pkt)

    async def handle_connections(self, websocket):
        """
            We handle our server connections from here.
            Primary job is to simply read messages and send it to 
            handle_messages function
        """
        peer_addr=(websocket.remote_address[0], websocket.remote_address[1])
        self.server_connections.add(websocket)

        print(f"Inbound Connection from {peer_addr[0]}:{peer_addr[1]}")
        
        try:
            await self.send_room_hello(websocket)
            async for raw in websocket:
                try:
                    msg=json.loads(raw)
                    if not isinstance(msg, dict):
                        continue
                    await self.handle_messages(websocket, msg)
                except ConnectionClosed:
                    raise
                except Exception as e:
                    # A peer controls every byte of this message. One that is
                    # malformed used to raise straight out of the loop and
                    # drop the connection.
                    print(f"Discarding bad message from {peer_addr}: {e}")

        except ConnectionClosed:
            print(f"Inbound Connection Closed: {peer_addr}")

        finally:
            self.server_connections.discard(websocket)
            self.admitted.discard(websocket)
            self.ws_public_keys.pop(websocket, None)
            self._room_challenges.pop(websocket, None)
            await websocket.close()
            await websocket.wait_closed()

    async def broadcast_message(self, pkt):
        # For broadcasting messages to all the connections we have

        targets=self.server_connections | self.client_connections
        if self.manifest:
            targets={ws for ws in targets if ws in self.admitted}
        for ws in targets:
            try:
                await ws.send(json.dumps(pkt))

            except Exception as e:
                print(f"Error broadcasting: {e}")
                if ws in self.server_connections:
                    self.server_connections.discard(ws)
                else:
                    normalized_endpoint = normalize_endpoint((ws.remote_address[0], ws.remote_address[1]))
                    self.client_connections.discard(ws)
                    self.outbound_peers.discard(normalized_endpoint)
                    self.got_pong.pop(ws, None)
                    self.have_sent_peer_info.pop(ws, None)
                await ws.close()
                await ws.wait_closed()

    async def create_and_broadcast_tx(self, receiver_public_key, payload):
        """
            Function to create and broadcast transactions
        """
        transaction=Transaction(payload, self.wallet.public_key_pem, receiver_public_key)
        transaction_str=str(transaction)
        
        signature=self.wallet.private_key.sign(
            transaction_str.encode(),
        )

        transaction.sign=signature

        signature_b64=base64.b64encode(signature).decode()
        # b64encode returns bytes, Decode converts bytes to string
        
        pkt={
            "type":"new_tx",
            "id":str(uuid.uuid4()),
            "transaction":transaction_str,
            "sign":signature_b64,
            "sender_pem":self.wallet.public_key_pem # Already available as a pem string as defined in constructor
        }
        
        remember_message_id(self.seen_message_ids, pkt["id"])
        if self.chain.transaction_exists_in_chain(transaction):
            return
        
        async with self.mem_pool_lock:
                self.mem_pool.append(transaction)

        print("Transaction Created", transaction)
        print("\n")
        await self.broadcast_message(pkt)

    def get_contract_state(self, contract_id):
        for block in reversed(self.chain.chain):
            for transaction in reversed(block.transactions):
                if transaction.receiver == "invoke" and transaction.payload[0] == contract_id:
                    return transaction.payload[3]
        return {}

    async def user_input_handler(self):
        """
            A function to constantly take input from the user 
            about whom to send and how much
        """
        while True:
            print("Block Chain Menu\n***************")
            if(self.staker):
                print("0) Quit\n1) Add Transaction\n2) View balance\n3) Print Chain\n4) Print Pending Transactions\n5) Print Current Stakers\n6) Time since last epoch\n7) Send Files\n8) Download Files\n9) Stake\n")
            else:
                print("0) Quit\n1) Add Transaction\n2) View balance\n3) Print Chain\n4) Print Pending Transactions\5) Print Current Stakers\n6) Time since last epoch\n7) Send Files\n8) Download Files\n")

            ch= await asyncio._get_running_loop().run_in_executor(
                None, input, "Enter Your Choice: "
            )
            try:
                ch=int(ch)
            except ValueError:
                print("\nPlease enter a valid number!!!\n")
                continue

            if ch==1:
                rec = await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter Receiver's Name or Public Key: "
                )

                if rec == "deploy":
                    contract_code = get_contract_code_from_notepad()
                    if not contract_code:
                        print("Contract code field is empty")
                        continue
                    gas_used = len(contract_code)//10 + BASE_DEPLOY_COST
                    amount = gas_used * GAS_PRICE
                    payload = [contract_code, amount]

                    if amount<=self.chain.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)):
                        await self.create_and_broadcast_tx(rec, payload)
                    else:
                        print("Insufficient Account Balance")
                elif rec == "invoke":
                    contract_id = await asyncio._get_running_loop().run_in_executor(
                        None, input, "\nEnter Contract Id: "
                    )
                    if contract_id not in self.contractsDB.contracts:
                        print("No such contract found...")
                        continue

                    func_name = await asyncio._get_running_loop().run_in_executor(
                        None, input, "\nEnter Function Name: "
                    )

                    args = []
                    loop = asyncio.get_running_loop()
                    arg_number = 1
                    while True:
                        arg = await loop.run_in_executor(None, input, f"Enter argument {arg_number} (or \\q to finish): ")
                        if arg.strip() == "\\q":
                            break
                        try:
                            parsed_arg = ast.literal_eval(arg)
                        except Exception:
                            parsed_arg = arg
                        args.append(parsed_arg)
                        arg_number += 1

                    response = self.run_contract([contract_id, func_name, args])
                    if(response["error"] != None):
                        print("Error: ", response["error"])
                        continue
                    state = response["state"]
                    gas_used = response["gas_used"]
                    amount = gas_used * GAS_PRICE

                    payload = [contract_id, func_name, args, state, amount]

                    if amount<=self.chain.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)):
                        await self.create_and_broadcast_tx(rec, payload)
                    else:
                        print("Insufficient Account Balance")
                else:
                    amt= await asyncio._get_running_loop().run_in_executor(
                        None, input, "\nEnter Amount to send: "
                    )

                    receiver_public_key = self.name_to_public_key_dict.get(rec.lower().strip())

                    if receiver_public_key is None:
                        rec_split = rec.split("\\n")
                        rec_refined = "\n".join(rec_split)
                        exist = 0
                        for (nme, pk) in self.name_to_public_key_dict.items():
                            if pk == rec_refined:
                                receiver_public_key = pk
                                exist = 1
                                break
                        if exist == 0:
                            print("No person available in directory with provided name or public key...")
                            continue
                    
                    try:
                        amt=float(amt)
                    except ValueError:
                        print("Amount must be a number")
                        continue

                    if(amt<=0):
                        print("\nAmount must be positive\n")
                        continue

                    if amt<=self.chain.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)):
                        await self.create_and_broadcast_tx(receiver_public_key, amt)
                    else:
                        print("Insufficient Account Balance")
            
            elif ch==2:
                print("Account Balance =",self.chain.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)))

            elif ch==3:
                i=0
                # We print all the blocks
                if(not self.chain):
                    print("\nChain hasn't been initialized yet\n")
                    continue
                for block in self.chain.chain:
                    print(f"block{i}: {block}\n")
                    i+=1

            elif ch==4:
                i=0
                for transaction in self.mem_pool:
                    print(f"transaction{i}: {transaction}\n\n")
                    i+=1

            elif ch==5:
                async with self.curr_stakers_condition:
                    print("\n")
                    for key in self.current_stakers:
                        print(f"{key}:{self.current_stakers[key]}\n")
                    print("\n")

            elif ch==6:
                print(f"\n{(datetime.now()-self.last_epoch_end_ts).seconds}\n")

            elif ch==7:
                desc= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter description of file: "
                )
                path= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter path of file: "
                )
                pkt=await self.uploadFile(desc, path)
                await self.broadcast_message(pkt)

            elif ch==8:
                cid= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter cid of file: "
                )
                path= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter path to download the file: "
                )
                download_ipfs_file_subprocess(cid, path)

            elif ch==9:
                if(not self.staker):
                    continue
                amt= await asyncio._get_running_loop().run_in_executor(
                    None, input, "\nEnter Amount to stake: "
                )
                try:
                    await self.stake_and_schedule(int(amt))
                except ValueError as e:
                    print("\nPlease enter a valid number!!!\n", e)
                except Exception as e:
                    print("\nUnexpected error occured!!!\n", e)

            elif ch==0:
                print("Quitting...")
                break
    
    async def uploadFile(self, desc: str, path:str):
        file_path=Path(path)
        if(not file_path.is_file()):
            print("\nFile doesn't exist\n")
            return

        if not self.daemon_process: 
            self.start_daemon()
        
        cid, name = await asyncio.to_thread(addToIpfs, path)
        if(not(cid and name)):
            return
        
        print(f"\nNew File Created : {cid}\n")
        pkt={
            "type":"file",
            "id":str(uuid.uuid4()),
            "desc":desc,
            "cid":cid
        }
        
        remember_message_id(self.seen_message_ids, pkt["id"])
        async with self.file_hashes_lock:
            self.file_hashes[cid]=desc
        return pkt

    def init_repo(self):
        """
            Creates a ipfs repo of name ending in ipfs_port_no eg ipfs_5000 
        """
        if not self.repo_path.exists():
            subprocess.run(["ipfs", "init"], env=self.env, check=True)
            print("\nIPFS repo created\n")

    def configure_ports(self):
        subprocess.run(["ipfs", "config", "Addresses.API", f"/ip4/127.0.0.1/tcp/{self.ipfs_port}"], env=self.env, check=True)
        subprocess.run(["ipfs", "config", "Addresses.Gateway", f"/ip4/127.0.0.1/tcp/{self.gateway_port}"], env=self.env, check=True)
        subprocess.run([
            "ipfs", "config", "Addresses.Swarm", "--json",
            f'["/ip4/127.0.0.1/tcp/{self.swarm_tcp}", "/ip4/127.0.0.1/udp/{self.swarm_udp}/quic"]'
        ], env=self.env, check=True)
        print("\nConfigured Ports\n")

    def start_daemon(self):
        self.daemon_process= subprocess.Popen(["ipfs", "daemon"], env=self.env)
        print("\nIPFS Daemon Started\n")

    def stop_daemon(self):
        if self.daemon_process:
            self.daemon_process.terminate()
            self.daemon_process.wait()

    async def connect_to_peer(self, host, port):
        """
            Function to form an outbound connection to the given host:port
            and handle messages that come form this connection
            Also initiates the handshake
        """

        endpoint=(host, port)
        if endpoint in self.outbound_peers or endpoint==(self.host, self.port):
            return

        uri=f"ws://{host}:{port}"
        
        websocket = None
        try:
            websocket=await websockets.connect(uri)
            self.client_connections.add(websocket)
            self.outbound_peers.add(endpoint)
            self.have_sent_peer_info[websocket]=False

            print(f"Outbound connection formed to {host}:{port}")
            await self.send_room_hello(websocket)
            
            pkt = None
            # If connecting first time to the network, broadcasts node information to the entire network
            if self.chain == None:
                pkt={
                    "type":"add_peer",
                    "id":str(uuid.uuid4()),
                    "data":{
                        "host":self.host,
                        "port":self.port,
                        "name":self.name,
                        "public_key":self.wallet.public_key_pem
                    }
                }
            else:
                pkt={
                    "type":"ping",
                    "id":str(uuid.uuid4()),
                } 

            remember_message_id(self.seen_message_ids, pkt["id"])
            await websocket.send(json.dumps(pkt))

            async for raw in websocket:
                try:
                    msg=json.loads(raw)
                    if not isinstance(msg, dict):
                        continue
                    await self.handle_messages(websocket, msg)
                except ConnectionClosed:
                    raise
                except Exception as e:
                    print(f"Discarding bad message from {host}:{port}: {e}")
        except Exception as e:
            print(f"Failed to connect to {host}:{port} ::: {e}")
        finally:
            self.outbound_peers.discard(endpoint)
            if(websocket):
                self.admitted.discard(websocket)
                self.ws_public_keys.pop(websocket, None)
                self._room_challenges.pop(websocket, None)
                self.client_connections.discard(websocket)
                self.got_pong.pop(websocket, None)
                self.have_sent_peer_info.pop(websocket, None)
                await websocket.close()
                await websocket.wait_closed()

    async def discover_peers(self):
        """
            Maintains up to MAX_CONNECTIONS peers.
            Connects only to fill the pool if under MAX_CONNECTIONS.
        """

        while True:
            if len(self.outbound_peers) < self.params.max_connections:
                potential_peers = {
                    endpoint for endpoint in self.known_peers
                    if endpoint not in self.outbound_peers and endpoint != (self.host, self.port)
                }
                while len(self.outbound_peers) < self.params.max_connections and potential_peers:
                    new_peer = get_random_element(potential_peers)
                    potential_peers.discard(new_peer)
                    if new_peer:
                        asyncio.create_task(self.connect_to_peer(*new_peer))
                        await asyncio.sleep(1)
            await asyncio.sleep(30)

    async def gossip_peer_sampler(self):
        """
            Every 60s, drops one existing peer and connects to one new peer.
        """
        while True:
            await asyncio.sleep(60)
            if len(self.known_peers) <= len(self.outbound_peers) or len(self.outbound_peers) < self.params.max_connections:
                continue  # Nothing to swap

            # Disconnect one random client connection
            to_drop = get_random_element(self.client_connections)
            if to_drop:
                print(f"Gossip Sampling: Disconnecting {to_drop.remote_address}")
                self.client_connections.discard(to_drop)
                normalized_endpoint = normalize_endpoint((to_drop.remote_address[0], to_drop.remote_address[1]))
                self.outbound_peers.discard(normalized_endpoint)
                self.got_pong.pop(to_drop, None)
                self.have_sent_peer_info.pop(to_drop, None)
                await to_drop.close()
                await to_drop.wait_closed()

            # Connect to a new peer (not already connected)
            potential_peers = {
                endpoint for endpoint in self.known_peers
                if endpoint not in self.outbound_peers and endpoint != (self.host, self.port)
            }

            if potential_peers:
                new_peer = get_random_element(potential_peers)
                if new_peer:
                    print(f"Gossip Sampling: Connecting to new peer {new_peer}")
                    asyncio.create_task(self.connect_to_peer(*new_peer))

    async def send_stake_announcements(self, amt: int):
        """
            Used for sending stake announcements
        """
        if self.manifest:
            self.register_stake(amt)
            return
        new_stake=Stake(self.wallet.public_key_pem, amt)
        stake_dict=new_stake.to_dict()

        sign=self.wallet.private_key.sign(str(new_stake).encode())
        new_stake.sign=sign

        stake_dict["sign"]=base64.b64encode(sign).decode()
        pkt={
            "id":str(uuid.uuid4()),
            "type":"stake_announcement",
            "public_key":self.wallet.public_key_pem,
            "stake":stake_dict
        }

        remember_message_id(self.seen_message_ids, pkt["id"])
        async with self.curr_stakers_condition:
            self.current_stakers[self.wallet.public_key_pem]=amt
            self.current_stakes.add(new_stake)

        self.staked_amt=amt
        print("Stake Created")
        await self.broadcast_message(pkt)

    async def restart_epoch(self):
        while True:
            await asyncio.sleep(self.epoch_time/2)
            currTime=datetime.now()
            if(currTime-self.last_epoch_end_ts>timedelta(seconds=self.epoch_time*7/6)):
                self.last_epoch_end_ts=datetime.now()
                self.staked_amt=0
                self.reset_stake_snapshot()

    def try_produce_block(self):
        """
            Run the stake lottery for the current epoch and, on a win, build,
            sign and append a block holding every pending transaction and event.
            Returns the block, or None when there was nothing to include or the
            lottery was lost. Shared by the network loop and in-process callers.
        """
        if not self.staker or not self.current_stakers:
            return None
        pending_transactions=[t for t in self.mem_pool if not self.chain.transaction_exists_in_chain(t)]
        pending_events=list(self.event_pool)
        if not pending_transactions and not pending_events:
            return None

        # Consecutive blocks must respect the room's minimum spacing or every
        # validator (including our own restart validation) would reject it.
        if datetime.now().timestamp()*1000 - self.chain.lastBlock.ts < self.params.min_block_spacing_seconds*1000:
            return None

        seed=self.chain.epoch_seed()
        vrf_output_int=core.vrf_output_int(self.wallet.public_key_pem, seed)
        total_stake=sum(self.current_stakers.values())
        if self.staked_amt<=0 or not core.is_eligible(vrf_output_int, self.staked_amt, total_stake):
            return None

        newBlock=Block(self.chain.lastBlock.hash, pending_transactions)
        newBlock.files=self.file_hashes.copy()
        newBlock.events=pending_events
        newBlock.seed=seed
        newBlock.vrf_proof=core.vrf_prove(self.wallet.private_key, seed)
        newBlock.staked_amt=self.staked_amt
        newBlock.creator=self.wallet.public_key_pem
        newBlock.stakers=core.sort_snapshot(self.current_stakes)
        newBlock.sign=self.wallet.private_key.sign(str(newBlock).encode())

        with self.state_lock:
            if not self.chain.isValidBlock(newBlock, self.ledger):
                return None
            self.chain.chain.append(newBlock)
            self.commit_block_events(newBlock)
        self.last_epoch_end_ts=datetime.now()
        for transaction in newBlock.transactions:
            if transaction.receiver == "deploy":
                self.deploy_contract(transaction)

        self.staked_amt=0
        self.reset_stake_snapshot()
        return newBlock

    async def stake_and_schedule(self, amt: int) -> bool:
        """
            Register a stake for the current epoch, announce it, and schedule
            block creation at the end of the epoch. Returns False (with a
            printed reason) when staking is not currently possible.
        """
        currTime=datetime.now()
        time_since=currTime-self.last_epoch_end_ts
        if self.staked_amt>0:
            print("Can't sent multiple stakes in one epoch")
            return False

        if time_since>timedelta(seconds=self.epoch_time*5/6):
            if time_since>timedelta(seconds=self.epoch_time*7/6):
                self.last_epoch_end_ts=datetime.now()
                self.staked_amt=0
                self.reset_stake_snapshot()
                time_since=timedelta(seconds=0)
            else:
                print(f"\nStake registration period closed, next epoch in {self.epoch_time-time_since.total_seconds():.1f}s\n")
                return False

        if amt<=0 or amt<self.params.minimum_stake:
            print("\nInvalid amount\n")
            return False
        if not self.manifest and amt>self.chain.calc_balance(self.wallet.public_key_pem, self.mem_pool, list(self.current_stakes)):
            print("\nInsufficient bank balance\n")
            return False

        await self.send_stake_announcements(amt)
        self.staked_amt=amt
        time_left=max(0.0, self.epoch_time-time_since.total_seconds())
        print(f"Creating block in {time_left:.1f} seconds")
        asyncio.create_task(self.create_blocks(time_left))
        return True

    async def auto_stake_loop(self, amt: int):
        """
            Headless block production: whenever there is pending work and this
            node has not staked this epoch, stake `amt` and let create_blocks
            run the lottery at the end of the epoch.
        """
        while True:
            await asyncio.sleep(max(0.05, self.epoch_time/6))
            if self.chain is None or self.staked_amt>0:
                continue
            if self.mem_pool or self.event_pool:
                try:
                    await self.stake_and_schedule(amt)
                except Exception as e:
                    print(f"auto stake failed: {e}")

    async def create_blocks(self, time):
        if(not self.staker):
            return

        await asyncio.sleep(time)
        if(len(self.current_stakers)<=0):
            print("\nNo stakers\n")
            self.last_epoch_end_ts=datetime.now()
            self.staked_amt=0
            return

        async with self.curr_stakers_condition:# So that no new stakes come in
            newBlock=self.try_produce_block()
            if newBlock is None:
                print("\nNo block produced this epoch\n")
                self.last_epoch_end_ts=datetime.now()
                self.staked_amt=0
                self.reset_stake_snapshot()
                return

            print("\nYou won\n")
            pkt={
                "type":"new_block",
                "id":str(uuid.uuid4()),
                "block":newBlock.to_dict(),
                "vrf_proof":base64.b64encode(newBlock.vrf_proof).decode(),
                "sign":base64.b64encode(newBlock.sign).decode(),
            }
            remember_message_id(self.seen_message_ids, pkt["id"])
            await self.broadcast_message(pkt)
            if self.activate_disk_save == "y":
                self.save_chain_to_disk()
        self.last_epoch_end_ts=datetime.now()

        async with self.mem_pool_lock:
            for transaction in list(self.mem_pool):
                if newBlock.transaction_exists_in_block(transaction):
                    self.mem_pool.remove(transaction)

        async with self.file_hashes_lock:
            for hash in list(self.file_hashes.keys()):
                if newBlock.cid_exists_in_block(hash):
                    self.file_hashes.pop(hash, None)

    async def find_longest_chain(self):
        """
            We routinely check every 30 seconds, every other chain and we replace
            ours with theirs if theirs is >= ours
        """
        while True:
            pkt={
                "type":"chain_request",
                "id":str(uuid.uuid4())
            }
            remember_message_id(self.seen_message_ids, pkt["id"])
            await self.broadcast_message(pkt)
            print("\nSent out chain requests...")
            await asyncio.sleep(60)

    def calculate_contract_id(self, sender, timestamp):
        data = f"{sender}:{timestamp}"
        hash_object = hashlib.sha256(data.encode('utf-8'))
        return hash_object.hexdigest()
        
    def deploy_contract(self, transaction):
        sender = transaction.sender
        timestamp = transaction.ts
        code = transaction.payload[0]
        contract_id = self.calculate_contract_id(sender, timestamp)
        self.contractsDB.store_contract(contract_id, code)
        print("Contract deployed with id: ", contract_id)

    def run_contract(self, payload):
        contract_id, func_name, args = payload[0], payload[1], payload[2]
        code = self.contractsDB.get_contract(contract_id)
        if code is None:
            raise Exception(f"Contract '{contract_id}' not found.")

        state = self.get_contract_state(contract_id)
        executor = SecureContractExecutor(code)
        response = executor.run(func_name, args, state)

        return response

    async def start(self, bootstrap_host=None, bootstrap_port=None, interactive=True, auto_stake=None):
        """
            interactive=False runs headless (no stdin menu) until stop() is
            called; used by the application runtime and the integration tests.
        """
        self.loop = asyncio.get_running_loop()
        self.stop_event = asyncio.Event()
        self.server = await websockets.serve(self.handle_connections, self.host, self.port)

        if self.chain is None:
            if self.manifest:
                # Every node in a room derives the same genesis from the
                # verified manifest and never adopts a different one.
                self.chain=Chain(genesis_block=room_manifest.build_genesis(self.manifest))
                self.chain.params=self.params
                self.rebuild_ledger()
            elif not (bootstrap_host and bootstrap_port):
                print("WARNING: no room manifest; using a self-signed legacy genesis")
                self.chain=Chain(publicKey=self.wallet.public_key_pem, privatekey=self.wallet.private_key)
                self.chain.params=self.params
        if self.chain is not None:
            self.last_epoch_end_ts=datetime.now()
        self.ready.set()

        # If a bootstrap node is given we connect to it (and, without a
        # manifest, take its chain).
        if bootstrap_host and bootstrap_port:
            normalized_bootstrap_host, normalized_bootstrap_port = normalize_endpoint((bootstrap_host, bootstrap_port))
            asyncio.create_task(self.connect_to_peer(normalized_bootstrap_host, normalized_bootstrap_port))

        tasks=[
            asyncio.create_task(self.restart_epoch()),
            asyncio.create_task(self.find_longest_chain()),
            asyncio.create_task(self.discover_peers()),
            asyncio.create_task(self.gossip_peer_sampler()),
        ]
        if auto_stake:
            tasks.append(asyncio.create_task(self.auto_stake_loop(auto_stake)))
        try:
            if interactive:
                await asyncio.create_task(self.user_input_handler())
            else:
                await self.stop_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            self.server.close()
            await self.server.wait_closed()

    def stop(self):
        """Ask a headless start() to return. Safe from any thread."""
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.stop_event.set)
