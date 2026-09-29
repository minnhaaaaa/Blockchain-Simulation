# AgentGuard Lite: Technical Stack and Interfaces

## 1. Stack principles

The stack is intentionally small because the first executable release has a 24-hour deadline and must extend the existing repository rather than replace it. Existing dependencies are reused where they are suitable. New infrastructure is avoided unless it directly satisfies a required feature.

All operational values are injected at runtime. The stack must not rely on hardcoded hosts, ports, rooms, nodes, peers, wallets, paths, policies, jobs, rewards, models, or demo data.

## 2. Languages and runtime

| Area | Technology | Reason |
|---|---|---|
| Backend and blockchain | Python 3.10+ | Existing implementation and team delivery speed |
| Asynchronous networking | `asyncio` | Already used by the node runtime |
| P2P transport | `websockets` 15.x | Already used for direct node connections |
| Web and JSON API | Flask 3.x | Already declared in the repository and sufficient for the MVP |
| Local HTTP serving | Flask CLI/Werkzeug | Directly supports the local MVP without an additional integration layer |
| Frontend | HTML5, CSS3, vanilla JavaScript | No build pipeline or additional framework dependency |
| Relational/runtime storage | Python `sqlite3` | Built into Python, transactional, inspectable, and adequate locally |
| Structured data | JSON with canonical serialization | Human-readable transport and deterministic signing input |
| Tests | `unittest` and `unittest.IsolatedAsyncioTestCase` | Built into Python; no dependency installation risk |

React, TypeScript, Docker, Redis, PostgreSQL, Kafka, Celery, and a CSS framework are not required for P0. Adding them within the 24-hour milestone would create setup and integration cost without proving additional project requirements.

## 3. Existing libraries retained

| Library | Use |
|---|---|
| `ecdsa` with SECP256k1 | Existing wallet, transaction, stake, block, and receipt signatures |
| `hashlib` SHA-256 | Content hashes, canonical record hashes, and deterministic pseudo-VRF output |
| `websockets` | Node-to-node P2P messages and chain synchronization |
| Flask | Signalling endpoints, dashboard APIs, and HTML serving |
| Hypercorn | Retained for a later ASGI deployment path; not required by P0 launch commands |
| `requests` | Optional configured model-provider calls and service health checks |
| `RestrictedPython` | Retained for the existing smart-contract subsystem, not used as the P0 agent sandbox |
| `ipfshttpclient` | Optional P1 artifact adapter only; P0 cannot require a running IPFS daemon |
| `psutil` | Existing process/resource support where needed |

The current arbitrary smart-contract executor is not the AgentGuard permission boundary. P0 agent tools are explicitly registered Python functions with typed inputs and bounded behavior.

## 4. Proposed package structure

```text
Blockchain-Simulation/
├── agentguard/
│   ├── __init__.py
│   ├── config.py             # configuration sources and validation
│   ├── schemas.py            # jobs, policies, actions, decisions, receipts
│   ├── canonical.py          # canonical JSON and hashing helpers
│   ├── artifacts.py          # content-addressed job artifact storage
│   ├── policy.py             # deny-by-default evaluator
│   ├── tools.py              # bounded registered tools
│   ├── worker.py             # action proposal and execution loop
│   ├── providers.py          # provider interface and optional adapters
│   └── node_service.py       # narrow adapter to the PoS node
├── signalling/
│   ├── __init__.py
│   ├── app.py                # join, heartbeat, peers, leave endpoints
│   ├── registry.py           # SQLite-backed room membership
│   └── client.py             # node discovery client
├── web/
│   ├── app.py                # dashboard and application APIs
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js
│       └── styles.css
├── tests/
│   ├── fixtures/             # test-only external inputs
│   ├── test_pos_*.py
│   ├── test_signalling.py
│   ├── test_policy.py
│   ├── test_events.py
│   └── test_end_to_end.py
├── consensus/pos/            # corrected PoS implementation
├── storage/                  # changed to room/node-namespaced state
├── PLAN.md
└── TECH_STACK.md
```

The exact filenames may change during implementation, but package ownership and separation must remain: consensus must not depend on Flask, and the web layer must not manipulate chain internals directly.

## 5. Process topology

The local MVP contains independently startable processes:

```text
                         ┌──────────────────────┐
                         │  Signalling service  │
                         │ room membership only │
                         └──────────┬───────────┘
                                    │ join / heartbeat / list
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
          ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
          │  PoS node A │◄──►│  PoS node B │◄──►│  PoS node C │
          └──────┬──────┘    └─────────────┘    └─────────────┘
                 │ narrow node service
          ┌──────▼────────────────────────────────────────────┐
          │ Flask application API + AgentGuard worker/gateway │
          └──────┬────────────────────────────────────────────┘
                 │ JSON over HTTP
          ┌──────▼──────┐
          │ Web browser │
          └─────────────┘
```

The signalling service can fail after peers connect without invalidating the blockchain. It never creates blocks, chooses validators, approves actions, or stores private keys.

When a room is created, its first node generates and signs a room manifest. The signalling service stores and returns that immutable manifest, but other nodes verify its signature and genesis descriptor themselves. The manifest supplies the room's protocol and consensus configuration; it is not a server-authored source of truth.

## 6. Configuration strategy

Configuration precedence is:

1. Explicit command-line arguments.
2. Environment variables.
3. A configuration JSON file explicitly selected at launch.

There are no invisible operational defaults. Missing required values cause startup to fail with a precise validation message. Optional values are absent rather than silently invented.

Required signalling configuration:

- Bind host
- Bind port
- SQLite database path
- Membership TTL
- Maximum accepted request size

Required node configuration:

- Advertised host and P2P port
- Node name
- Room ID
- Signalling service URL
- Per-node storage directory
- Consensus configuration reference or complete consensus parameters
- Whether the node participates as a validator
- Whether a named malicious scenario is enabled

Required room manifest fields, generated or supplied at room creation:

- Room ID
- Protocol/schema version
- Consensus type and complete consensus parameters
- Genesis block descriptor or canonical genesis hash inputs
- Creator public key
- Creation timestamp
- Creator signature

Required application configuration:

- API bind host and port
- Data root
- Connected node identity/service reference
- Upload size limit
- Poll interval or event-stream setting

Optional model-provider configuration:

- Provider type
- Base URL
- Model identifier
- Credential environment-variable name, never the credential itself in a committed file
- Request timeout

Configuration example files contain documented placeholders and are never automatically loaded. Real configuration files containing keys or machine-specific paths must be ignored by Git.

## 7. Identity and cryptography

### Node and user identity

- Each node generates an ECDSA SECP256k1 keypair on first launch unless an explicit persisted key location is supplied.
- Private keys remain in that node's configured storage directory.
- Node IDs are derived or generated at runtime and stored per node.
- Public keys identify actors in signed ledger events.
- Display names are labels, not security identities.

### Canonical signing

All signed structures use one canonical JSON encoder:

- UTF-8 encoding
- Sorted object keys
- Compact separators
- No unsupported floating-point values
- Explicit schema version
- Signature field excluded from the bytes being signed

The same canonical bytes are used by producers and validators. Calling `str()` on arbitrary Python objects, sets, or unsorted dictionaries is not acceptable for consensus signatures.

### Pseudo-VRF scope

For the educational PoS simulation, the validator derives a deterministic signature/proof from the epoch seed and hashes it into a numeric output. Validators verify the proof, derive the same output, and compare it with the stake-weighted threshold. Documentation must call this a deterministic pseudo-VRF unless a standards-based VRF implementation replaces it.

## 8. Network protocols

### Signalling API

All request bodies and responses are JSON. Route names are structural API definitions, not runtime data.

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/rooms` | Store a newly generated, creator-signed room manifest |
| `GET` | `/api/rooms/{room_id}` | Retrieve the immutable room manifest |
| `POST` | `/api/rooms/{room_id}/members` | Join or replace the caller's membership |
| `POST` | `/api/rooms/{room_id}/members/{node_id}/heartbeat` | Extend a live membership |
| `GET` | `/api/rooms/{room_id}/members` | List non-expired room peers |
| `DELETE` | `/api/rooms/{room_id}/members/{node_id}` | Leave the room |
| `GET` | `/health` | Liveness only |

The room-create body contains the runtime-generated signed manifest. The service rejects replacement of an existing manifest. The join body contains runtime-supplied node ID, name, advertised endpoint, public-key fingerprint, and timestamp. The server derives expiry using configured TTL and server time.

### Existing P2P protocol

After discovery, nodes continue to use direct WebSocket connections for:

- Ping/pong
- Peer identity exchange
- Known-peer exchange
- Chain requests and responses
- Transaction/event propagation
- Stake announcements
- Block propagation
- Fork/evidence messages

Every inbound message requires schema validation, size bounds, and safe handling of missing fields. Discovery data is untrusted until the P2P identity handshake succeeds.

## 9. Application API

The P0 web/API surface is:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/status` | Node, room, provider, and service status |
| `GET` | `/api/peers` | Discovered and connected peer summaries |
| `GET` | `/api/chain` | Chain height and recent block summaries |
| `GET` | `/api/stakes` | Current authenticated stake view |
| `POST` | `/api/artifacts` | Upload a user-selected artifact |
| `POST` | `/api/jobs` | Create a job with a complete policy |
| `GET` | `/api/jobs` | List jobs derived from ledger/application state |
| `GET` | `/api/jobs/{job_id}` | Read a job and its ordered event timeline |
| `POST` | `/api/jobs/{job_id}/accept` | Worker accepts a job |
| `POST` | `/api/jobs/{job_id}/actions` | Submit an action proposal |
| `POST` | `/api/jobs/{job_id}/actions/{action_id}/decision` | Owner approves or rejects a waiting action |
| `POST` | `/api/jobs/{job_id}/run` | Run the configured worker for the job |
| `GET` | `/api/violations` | Read policy and validation violations |

APIs reject unknown fields where practical, return stable machine-readable error codes, and never substitute sample values for missing fields.

## 10. Storage

### Signalling database

SQLite stores room membership and heartbeat expiry. It contains no blockchain authority and can be recreated without changing ledger history.

### Node storage

State is namespaced as:

```text
<configured-node-data-root>/<room-id>/<node-id>/
```

It contains that node's key, identity, chain, and peer cache. Two local nodes must never share or overwrite the same key or chain file.

### AgentGuard application storage

Application storage is namespaced by room and job. Uploaded artifact filenames are not trusted as paths. The server generates an artifact ID, stores content below the configured root, computes a SHA-256 digest, and preserves the original name as metadata only.

SQLite stores indexes and queryable application projections. The blockchain remains the authority for finalized signed events; SQLite is a rebuildable read model and job-scoped tool workspace.

### IPFS

IPFS is P1 because it requires an external daemon and adds failure modes. An artifact-store interface permits later replacement of local content-addressed storage with IPFS. Only content identifiers or hashes belong on-chain; large files do not.

## 11. Agent and tool execution

### Provider interface

The provider receives the user job, available tool schemas, and prior action results. It returns a structured action proposal. Implementations may include:

- A configured local Ollama provider.
- A configured OpenAI-compatible HTTP provider.
- A manual provider where a worker submits an action through the API.

There is no production fake provider that silently generates a predetermined demonstration. Test doubles are confined to `tests/`.

### Enforcement path

```text
provider proposal
      ↓
schema validation
      ↓
policy evaluation ── deny ──► signed denial event
      │
      ├── approval required ─► wait for owner decision
      │
      └── allow
             ↓
       bounded tool registry
             ↓
       hash result/artifact
             ↓
       signed completion event
```

The provider cannot call tools directly. Only the gateway can dispatch registered tools after validation and policy evaluation.

## 12. Frontend

The dashboard uses server-rendered HTML for the initial shell and vanilla JavaScript `fetch` calls for data. Timed polling is the P0 live-update mechanism because it is simple and reliable. Server-Sent Events may replace or supplement it in P1.

Frontend rules:

- No hardcoded arrays of peers, blocks, jobs, actions, violations, or chart points.
- Forms start blank except for structural labels and user-facing help text.
- Select options that represent runtime entities come from APIs.
- Empty API results produce honest empty states.
- All actions show pending, accepted, finalized, or rejected server state; optimistic UI must not imply blockchain finality.
- Private keys, full uploaded documents, and provider credentials are never rendered.

## 13. Security controls for the MVP

- Deny-by-default policy evaluation.
- Strict JSON/schema validation.
- ECDSA signatures for ledger actors.
- Canonical hashes and event chaining.
- Duplicate ID and sequence protection.
- Expiry checks for jobs, memberships, and receipts where configured.
- Resource IDs instead of arbitrary paths.
- Path normalization and containment checks.
- File-size and request-size limits from configuration.
- Read-only SQL enforcement and job-specific SQLite databases.
- Registered tools only; no shell and no arbitrary Python.
- Explicit user approval for policy-selected actions.
- Escaped UI output and safe download headers.
- Malicious behavior executed as named scenarios, never hidden in normal mode.

This does not provide strong isolation against hostile Python code because hostile arbitrary code is not allowed in P0. It also does not make shared-model activations private or verify remote neural-network computation.

## 14. Testing stack and commands

Use the standard library test runner:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Test layers:

- Pure unit tests for canonicalization, policies, event transitions, eligibility, and signatures.
- Async unit tests for peer and signalling clients.
- Flask test-client tests for HTTP contracts.
- Temporary-directory integration tests for storage isolation.
- Multi-process end-to-end test for signalling, three nodes, one job, one finalized receipt, and malicious rejections.
- Manual browser acceptance using the checklist in `PLAN.md`.

Tests use temporary directories and dynamically allocated ports. A test must not assume that a particular local port is free.

## 15. Dependency policy

P0 should work with the existing `requirements.txt` plus Python's standard library. If implementation reveals a genuinely necessary dependency, it must be:

- Added with an exact version.
- Used directly by a required feature.
- Documented here and in the setup instructions.
- Tested from a clean environment.
- Approved by both developers before the release freeze.

No dependency may be introduced solely for visual polish or to avoid writing a small, testable adapter.

## 16. Future extension path

After the 24-hour release, the interfaces support incremental additions:

1. Replace or supplement the provider with a Pooled/WebGPU room adapter.
2. Add redundant execution and challenge tasks for remote-compute verification.
3. Add worker qualification, capability declarations, reputation, and configurable rewards.
4. Add IPFS or another content-addressed artifact backend.
5. Introduce stronger process/container isolation for richer tools.
6. Add privacy-preserving execution only after defining an explicit threat model.
7. Replace the educational pseudo-VRF with a standards-based VRF implementation.

These extensions must preserve the core separation: inference proposes actions, the permission gateway controls execution, and the blockchain records independently verifiable state transitions.
