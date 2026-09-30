# Certa
A live, policy-controlled execution workspace backed by a room-discovered Proof-of-Stake simulation, Python APIs, and React.

Formerly AgentGuard. Internal module names and signed protocol identifiers remain unchanged for compatibility.

Start with the [live demo runbook](docs/LIVE_DEMO.md). It covers installation, operator configuration, real sign-in, uploads, approvals, tool execution, downloads, and multi-node verification. There are no seeded jobs or dashboard records.

For prompt-first AI tasks, fill the server-only `agent-provider.local.json` using [the example](agent-provider.example.json). Supply your OpenAI-compatible base URL, tool-capable model ID and API key. Without these values the agent is explicitly unavailable; Advanced setup still supports manual actions. The [runbook](docs/LIVE_DEMO.md#connect-your-ai-agent) explains permissions and which data is sent to the model.

## AgentGuard Lite implementation package

The next milestone turns the simulator into a room-discovered, policy-controlled agent execution network with a React interface. These documents are the frozen starting point for the three parallel implementation workstreams:

- [Implementation plan](PLAN.md)
- [Technical stack](TECH_STACK.md)
- [Data schemas and state machines](docs/SCHEMAS.md)
- [HTTP and node-service contract](docs/API_CONTRACT.md)
- [React product/interface specification](docs/FRONTEND_SPEC.md)
- [Developer 1: protocol and PoS](docs/DEV_1_PROTOCOL.md)
- [Developer 2: signalling and runtime](docs/DEV_2_RUNTIME.md)
- [Developer 2 implementation guide](docs/DEV_2_IMPLEMENTATION.md)
- [Developer 3: React and integration](docs/DEV_3_FRONTEND.md)
- [Developer 3 implementation and demo runbook](docs/DEV_3_IMPLEMENTATION.md)

Machine-readable contracts live in [`contracts/`](contracts/). This planning package specifies the target implementation; features remain subject to the definition of done in `PLAN.md` until their code and tests are merged.

## Features
- Peer-to-Peer network with decentralized communication
- Public/private key-based account system
- Digital signature verification
- Selectable consensus mechanism - PoW, PoS, PoA
- Smart contract deployment
- IPFS integration
- Persistent storage
- Malicious node to test security
- Command line interface, HTTP API, and React execution console

## React console

```bash
cd frontend
npm ci
npm run check
npm run demo -- --configure .demo-state/operator-profile.json
npm run demo -- --config .demo-state/operator-profile.json
```

The launcher asks for operational settings once, then starts the configured number of real nodes, signalling, authenticated APIs, and Vite. Ports, identities, room ID, and credentials are generated; settings and genesis allocations come from your profile. See the [live demo runbook](docs/LIVE_DEMO.md).

## Contents
- [Theory](#theory)
- [About this project](#about-this-project)
- [How to run this project](#how-to-run-this-project)

## Theory
### What is blockchain?
A blockchain is a decentralized, distributed digital ledger where data is stored in blocks linked together in a chain
- A block is made of list of transactions
### Peer-to-Peer Network
Since, there is no central authority, network is formed in a peer-to-peer fashion.
### Consensus Mechanism
Blockchain involves transactions in a trustless environment. So there is need for a mechanism to ensure integrity of the chain. There comes the need of consensus mechanisms. Each consensus mechanism ensures integrity of the chain in their own way.
#### Proof of Work(PoW)
- Nodes compete to solve a cryptographic puzzle
- The winner gets to add the next block to the chain
#### Proof of Stake(PoS)
- Nodes run vrf to generate vrf output and vrf proof to simulate a lottery system
- The winner of the lottery gets to generate the block.
#### Proof of Authority(PoA)
- A limited set of trusted nodes(authorities) validate and create new blocks
### Smart Contracts
- A smart contract is like a digital agreement written in code
- It sits on the blockchain and runs automatically when certain rules are met
### IPFS
Blockchains are not designed for storing large amount of data. That's where IPFS comes in.
- It's a decentralized file storage system
- Each file is identified by its content
- A unique hash called CID(Content Identifiers) is generated based on the content(Files with same content will have same CID)
- IPFS uses a Distributed Hash Table(DHT), similar to BitTorrent's Kademlia DHT
- When you request a CID, your node queries the DHT to ask "Which peers are providing this CID?"
- Nodes that have previously announced that CID to the DHT will be returned as providers
- Your node then directly connects to those providers via IPFS's peer-to-peer transport protocols(libp2p)

## About this project
### Basic Structure
Each **node** contains its own set of
- Known peers list (members of the network)
- Client connections (connection established by your node to other nodes)
- Server connections (connection established by other nodes to your node)
- Wallet (acts as your account in the network)
- Transaction pool (contains all transactions pending to be mined)
- Chain (personal copy of the blockchain)

Each **account** contains
- Private key
- Public key

**Transactions** are of 3 types

- **Coin Transaction** - To transfer money
  - Timestamp
  - Public key of the sender
  - Public key of the receiver
  - Transaction amount
- **Deploy Transaction** - To deploy contract
  - Timestamp
  - Public key of the sender
  - Contract code
  - Deploy charge

- **Invoke Transaction** - To invoke contract
  - Timestamp  
  - Public key of the sender  
  - Contract ID  
  - Function name  
  - Arguments  
  - New state  
  - Invoke charge  

Each **block** contains
- Timestamp
- List of transactions
- Hash of previous block
- Current block hash
- Miner info
- List of files
### Handshake Protocol
- Client: Sends ping
- Server: Receives ping &rightarrow; sends pong
- Client: Receives pong &rightarrow; Sends peer info (information about itself)
- Server: Receives peer info &rightarrow; adds it to its known peers (if not already present) &rightarrow; sends back known_peers (list of all nodes it knows)
- Client: Receives known_peers &rightarrow; adds new peers to its own known_peers &rightarrow; requests the chain
- Server: Receives chain request &rightarrow; sends its current chain
- Client: Receives the chain &rightarrow; replaces its own if the length of new chain is longer than the current one
### Peer-to-Peer Network
If the total number of nodes in the network is less than 10, it forms a mesh network. If the node count exceeds 9, Gossip-based Random Peer Sampling is used
- Each node maintains a list of 8 connected peers
- At regular intervals, a node drops one connection and connects to a new, previously unconnected peer from the known peers list
- This prevents network congestion by limiting the number of connections per node
- It also prevents sub-network formation by randomly switching connections  

**Implemented Using:** python websockets, asyncio
### Consensus Mechanism
Users can select their prefered consensus mechanism from the list of three available
#### Proof of Work(PoW)
- A new block is mined every 30 secs, if there are pending transactions in the transaction pool
- Mining nodes collect transactions into a block
- Node that first finds a valid hash gets the chance to mine
- Difficulty is set to 5. That means, a valid hash is the one which starts with five zeroes
- Nonce is incremented until finding a valid hash
- Once mined, the block is broadcasted to the network
- All nodes validate the block before adding it to their chain
#### Proof of Stake(PoS)
- An eligible validator may propose a block; an epoch can have no winner
- The timings are synchronized between peers based on the time since last block was created
- Each node can stake a certain amount of their cryptocurrency in order to run vrf.
- This implementation uses an educational deterministic pseudo-VRF, not a standards-based VRF
- If the vrf output generated by a node is less than (max value of vrf output) * (amount staked by this node/total amount staked by all nodes), then
- This node wins the lottery and create a block. (Notice that the greater the amount staked the greater the chance of winning the lottery)
- VRF Proof is used to check whether the one who claims to win the lottery actually generated the vrf output from the correct seed
- If node attempts double signing their stake is slashed.
- If multiple nodes win and creates blocks then the chain is forked.
- We use the heaviest chain rule to arrive at a consensus. (i.e the chain with the most amount staked is the valid chain)
#### Proof of Authority(PoA)
- Initially, admin, the one who started the chain is the only miner
- Admin can add or remove miners
- Each block can be mined only by the assigned miner
- If that miner is inactive, mining will be handed over to the next miner
### Smart Contracts
In this project
- Smart Contracts are written in python
- Users can write their own smart contracts and deploy
- Users can also invoke the deployed contract using their deployed address
- They run in a restricted educational executor with resource limits; this is not a production security boundary.

**Implemented Using:** RestrictedPython, multiprocessing
### IPFS
IPFS is integrated as a wrapper for the existing IPFS network. IPFS hashes of the user uploaded files are stored in the blocks. Other users can use this to download the file.  

**Implemented Using:** IPFS
### Persistent Storage
Persistent storage is implemented to enable nodes to reconnect to the network using there previous network data
### Malicious Node
- To test the security and robustness of our networks we created a malicious node that attempts
    1. Generate invalid transactions (amt>account balance or amount<=0)
    2. Double Sign
- Regression tests exercise malicious, replay, consensus, and multi-node cases; run the suite on your own host before making deployment claims.

## How to run this project
### Prerequisites
- `python 3.10+`
- `pip` (python package manager)
- `venv` (for creating virtual environment)
### Installation & Setup
Clone project into your local machine
```bash
git clone git@github.com:minnhaaaaa/Blockchain-Simulation.git
```
Enter into the project folder
```bash
cd Blockchain-Simulation
```
Create and activate virtual environment
```bash
python -m venv venv
# On macOS/Linux: source venv/bin/activate
# On PowerShell: .\venv\Scripts\Activate.ps1
```
Install dependencies
```bash
pip install -r requirements.txt
```
### AgentGuard backend

Create separate local JSON configuration files with operator-chosen values for signalling and each node. The required fields and room creation/join flow are documented in [Developer 2's implementation guide](docs/DEV_2_IMPLEMENTATION.md). Then run the signalling service and one API/node process per terminal:

```bash
python -m signalling --config <path-to-signalling-config.json>
python -m api --config <path-to-node-config.json>
python -m pytest -q tests
```

Each signed genesis allocation includes `public_key`, `amount`, and reserved validator `stake`; set `stake` to zero for observers. Node configuration now also requires `auth.session_ttl_seconds`; all node API calls except login require a Bearer session. The React dashboard uses these authenticated APIs.
### Terminal App
Start terminal app
```bash
python start_peer.py
```

sample:
  host: localhost
  port: 5000
  name: john

## Authors

**Rahan M**
[GitHub](https://github.com/Rahan-M) | [LinkedIn](https://www.linkedin.com/in/rahan-m-077a32254?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=android_app)

**Jefin Joji**
[GitHub](https://github.com/JefinCodes) | [LinkedIn](https://www.linkedin.com/in/jefin-joji-659354313?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=android_app)
