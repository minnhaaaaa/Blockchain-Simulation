# AgentGuard Lite: 24-Hour Implementation Plan

## 1. Project decision

AgentGuard Lite is a local, multi-node Proof-of-Stake network for executing agent tasks under explicit user-defined permissions. A user creates a job and supplies its inputs and policy. A worker proposes tool actions, the permission gateway allows, denies, or pauses each action for approval, and the blockchain records signed job and execution events. Honest workers can receive simulated rewards; malicious or replayed actions are rejected and shown in the web dashboard.

This is an executable research prototype, not a production AI sandbox, cryptocurrency, or distributed large-model inference engine. The 24-hour build proves the protocol surrounding agent execution. Pooled/WebGPU inference is a future adapter, not part of the first milestone.

## 2. Non-negotiable rule: no hardcoded runtime data

"Zero hardcoded data" means that production code must not contain operational, user, demo, or business data. Literal-free software is neither possible nor useful: protocol field names, status enums, API routes, error messages, and cryptographic domain-separation strings are structural code. Everything that can change between runs must come from configuration, user input, generated identity, discovered network state, or persisted state.

The following are prohibited in production code:

- Fixed room IDs, node IDs, node names, wallets, public/private keys, peer addresses, hostnames, ports, or bootstrap nodes.
- Pre-created users, workers, jobs, policies, transactions, blocks, balances, rewards, stakes, violations, or dashboard statistics.
- Embedded sample prompts, uploaded documents, expected agent actions, fake results, fake performance numbers, or a scripted demo path automatically loaded at startup.
- Absolute filesystem paths and assumptions about a developer's machine.
- Fixed model names, model endpoints, API keys, or provider credentials.
- Business values hidden as constants, including reward amounts, stake requirements, epoch duration, room expiry, connection limits, approval timeouts, and upload limits.
- UI components populated from JavaScript arrays that pretend to be live network data.
- Silent fallbacks that connect to localhost, invent a room, seed a chain, select a model, or approve an action when configuration is missing.

Every runtime value must have an identified source:

| Value | Required source |
|---|---|
| Room ID | User input or cryptographically generated value returned to the user |
| Node ID and wallet | Generated on first launch, then loaded from that node's storage directory |
| Node name | CLI, environment variable, or configuration file |
| Hosts and ports | CLI, environment variable, or configuration file |
| Peer list | Signalling server response and authenticated peer handshakes |
| Consensus parameters | Validated configuration shared by the room |
| Stake and reward values | User/network configuration and validated ledger state |
| Job description and inputs | Submitted by the user through the API/UI |
| Permission policy | Submitted with the job; deny is the behavior when no rule permits an action |
| Agent actions | Produced at runtime by the configured provider or submitted through the worker API |
| Decisions | Deterministic policy evaluation or explicit user approval |
| Dashboard content | Live API responses derived from node state |
| Timestamps and record IDs | Generated at runtime |
| Model provider and model | Explicit configuration; absence is reported, never silently replaced |

Test fixtures may contain fixed values only under `tests/fixtures/`. Production modules must never import or automatically load them. Demo inputs are uploaded explicitly in the same way as any other user input. A repository-wide review must verify that fixture data cannot enter a normal run.

## 3. MVP boundaries

### P0: must be complete

1. Correct and test the PoS validation path.
2. Start multiple independent nodes with separate identities and storage paths.
3. Create or join a room using a room ID through the signalling server.
4. Discover peers without a predefined bootstrap node.
5. Create a job from user-supplied data and a user-supplied policy.
6. Produce action proposals through a configurable worker interface.
7. Evaluate every action with deny-by-default permission rules.
8. Require explicit approval for policy-defined actions.
9. Sign and submit agent events to the blockchain.
10. Reject invalid signatures, unauthorized actions, duplicated event IDs, stale receipts, and replayed completion claims.
11. Display live peers, blocks, jobs, actions, decisions, and violations in a web interface.
12. Demonstrate at least one honest workflow and two malicious attempts.
13. Supply repeatable launch instructions and an evidence-based test report.

### P1: implement only after P0 passes

- A configurable Ollama or OpenAI-compatible planning provider.
- Server-Sent Events for live UI updates; timed polling is acceptable for P0.
- IPFS as an alternative to the P0 local content-addressed artifact store.
- Configurable simulated reward and penalty accounting.
- Worker qualification and reputation summaries.
- Exportable execution receipt.

### Explicitly out of scope for 24 hours

- WebGPU kernels or splitting model layers between devices.
- Token-by-token WebRTC inference.
- Executing arbitrary generated shell commands.
- Unrestricted generated Python execution.
- Public-internet deployment or untrusted-room privacy.
- Real money, tokens, NFTs, or carbon credits.
- Claims of verified AI correctness or production-grade isolation.
- Rewriting PoW and PoA unless a shared change is necessary for compatibility.

## 4. Core user journey

1. The operator starts a signalling server using an explicit configuration.
2. The first node creates a room manifest containing runtime-supplied consensus settings and a generated genesis descriptor; the signalling service stores the signed manifest without becoming a consensus participant.
3. Each additional node starts with its own configuration and joins the supplied room ID.
4. The signalling server returns the room manifest and currently live peers in that room.
5. Nodes verify the manifest and use the existing WebSocket protocol to connect directly and synchronize the chain.
6. A user opens the dashboard and submits a job, input artifacts, and a policy.
7. A worker accepts the job and proposes one action at a time.
8. The permission gateway evaluates the proposed action:
   - `allow`: execute using a registered tool.
   - `deny`: do not execute; record the reason.
   - `approval_required`: wait for the job owner to approve or reject it.
9. The worker hashes the result, signs an execution receipt, and submits an agent event transaction.
10. Validators verify the event, include it in a block, and finalize it through PoS.
11. The dashboard renders the resulting state from live node APIs.

## 5. Agent event model

Agent application records are signed canonical-JSON payloads carried by blockchain transactions. The event envelope must contain:

- `schema_version`
- `event_id`
- `event_type`
- `job_id`
- `actor_public_key`
- `sequence`
- `created_at`
- `payload`
- `previous_event_hash`, when the job already has history
- `signature`

P0 event types are:

- `job.created`
- `job.accepted`
- `action.proposed`
- `action.allowed`
- `action.denied`
- `action.approved`
- `action.rejected`
- `action.completed`
- `job.completed`
- `job.failed`
- `security.violation`

The payload is supplied at runtime and validated against the schema for its event type. Event IDs must be unique. Job event sequences must be monotonic. A completion must reference an accepted job, completed permitted actions, and the immediately preceding event hash. Validators must derive validity from the chain and payload; they must not trust UI state.

## 6. Permission and tool model

The gateway is deny-by-default. A missing or malformed policy never means allow.

A submitted policy defines:

- Permitted tool identifiers.
- Artifact IDs each tool may read.
- Artifact IDs or output namespaces each tool may write.
- Actions requiring human approval.
- Execution time and output-size limits.
- Optional job expiry.

P0 tools must be deterministic and bounded:

- Read a user-uploaded text or CSV artifact by artifact ID.
- Parse CSV using Python's standard library.
- Import structured rows into a job-scoped SQLite database.
- Execute read-only SQL after rejecting non-read operations.
- Write a text or JSON report to the job's output directory.
- Hash an artifact.

Workers must never receive a raw arbitrary filesystem path from an event. The server resolves user-owned artifact IDs inside the configured data root and rejects path traversal. Shell execution and arbitrary Python execution are not P0 tools.

## 7. PoS correction work

Before application events are trusted, the PoS path must satisfy all of the following:

- One canonical serialization function is used for hashing and signing.
- The signed block representation includes the previous hash, transactions, files, creator, stake amount, complete stake snapshot, epoch seed, proof, timestamp, and block ID.
- Stake entries are unique by staker identity, correctly signed, positive, affordable, and deterministically ordered.
- The creator's declared stake equals its authenticated stake in the snapshot.
- The total stake is nonzero and identical for block production and verification.
- Eligibility uses one boundary rule everywhere: the derived output must be strictly below the configured threshold.
- The pseudo-VRF proof is deterministic for a given key and epoch seed so a validator cannot grind randomized ECDSA signatures for a favorable result.
- A proof is verified against the creator's key and the exact epoch seed before its output is evaluated.
- A block hash changes whenever any consensus-relevant field changes.
- Duplicate transaction and event IDs are rejected across the relevant chain history and current block.
- Fork scoring uses only authenticated data and has a deterministic tie breaker.
- Double-signing evidence requires the same creator, height, and seed with two different signed block hashes; both signatures are verified against their respective blocks before a penalty is applied once.
- Serialized slash/finality state cannot differ between peers.
- Genesis handling is explicit and identical on every node in a room.

This project may accurately call the construction a deterministic pseudo-VRF simulation; it must not claim to implement a production cryptographic VRF unless an actual VRF library and test vectors are introduced.

## 8. Signalling design

The signalling service is a discovery registry, not a consensus authority. Its required operations are:

- Create a room by storing a creator-signed room manifest containing protocol version, consensus type, consensus parameters, genesis descriptor, creator public key, and creation timestamp.
- Read and verify the exact room manifest before a node joins.
- Join a room with node ID, advertised host, advertised port, name, public key fingerprint, and timestamp.
- Heartbeat an existing membership.
- List non-expired peers from the same room.
- Leave a room.
- Remove expired memberships using a configured TTL.

The room ID and manifest are never embedded in the server. The room creator generates them at runtime. The server must reject attempts to replace an existing room manifest, isolate rooms, and never return members from another room. A node connects to suitable discovered peers for a small demo network, using the existing P2P handshake for the actual connection and chain exchange. Consensus validity comes from signed blocks and the verified genesis descriptor, not from trusting the signalling database.

## 9. Web interface

The dashboard must contain live views for:

- Current room and node identity.
- Connected and discovered peers.
- Current chain height and recent blocks.
- Stake snapshot and latest proposer.
- Job creation form with artifact upload and policy editor/form.
- Job list and selected job timeline.
- Proposed actions awaiting approval.
- Allowed, denied, completed, and failed actions.
- Security violations and rejection reasons.
- Configured provider status, clearly showing when no model provider is configured.

The page starts empty and loads all content through APIs. Empty states must say that no data exists; they must not fabricate examples.

## 10. Work division for three people

### Person 1: consensus and blockchain lead

Owns existing consensus code and the ledger integration boundary.

Tasks:

- Write failing PoS unit tests for eligibility, stake snapshots, canonical hashes, duplicate events, replay, fork selection, and double signing.
- Fix `consensus/pos/blockchain_structures.py` and `consensus/pos/p2p.py` without copying fixes independently into multiple divergent implementations.
- Extract shared normal/malicious behavior where required so malicious mode changes attacks, not consensus validation.
- Add canonical serialization and deterministic signing/proof behavior.
- Define and validate the generic signed agent-event transaction envelope.
- Expose a narrow node service interface used by the application layer:
  - submit an event;
  - read chain summary;
  - read peer/stake summary;
  - read events by job ID;
  - subscribe or poll for state changes.
- Ensure per-node storage is namespaced by room and node ID.
- Review all code that can cause a ledger state transition.

Files owned primarily by Person 1:

- `shared_blockchain_structures.py`
- `consensus/pos/blockchain_structures.py`
- `consensus/pos/p2p.py`
- `consensus/pos/mal_node.py`
- Consensus and serialization tests

Person 1 must not build the dashboard or signalling UI unless Person 2 is blocked.

### Person 2: application, signalling, and web lead

Owns new AgentGuard modules and the user-facing flow.

Tasks:

- Implement configuration loading and strict startup validation.
- Implement the room signalling service and node discovery client.
- Define application schemas for jobs, policies, actions, decisions, artifacts, and receipts in agreement with Person 1's event envelope.
- Implement artifact ID resolution and job-scoped storage.
- Implement the deny-by-default permission gateway.
- Implement bounded CSV, SQLite, report-writing, and hashing tools.
- Implement the configurable provider interface; add a real provider only after the deterministic path works.
- Build Flask APIs and the HTML/CSS/JavaScript dashboard.
- Implement normal worker behavior plus API-triggered malicious scenarios for replay and unauthorized-action tests.
- Write signalling, policy, API, and end-to-end tests.
- Integrate against Person 1's narrow node service interface rather than importing consensus internals throughout the app.

Files owned primarily by Person 2:

- New `agentguard/` package
- New `signalling/` package
- New `web/` templates and static assets
- Application, signalling, API, and end-to-end tests
- Configuration schema and example templates

### Person 3: Verification coordinator



Tasks:

- Maintain a checklist of every command required to install and start the signalling server, nodes, and dashboard.
- Run the documented commands exactly as written on a clean terminal and record every failure verbatim for Persons 1 and 2.
- Create room IDs, node names, job text, policies, and uploaded demo inputs through the real UI during testing; do not edit source files to make the demo work.
- Execute the manual acceptance matrix supplied by the developers and mark pass/fail with timestamps.
- Capture screenshots of room creation, discovered peers, job submission, approval, finalized receipt, and malicious-action rejection.
- Verify that refreshing the page does not introduce fake data and that a new room begins empty.
- Search the UI and documentation for claims such as "secure," "verified," "private," or "distributed AI" and flag any claim not demonstrated by the build.
- Prepare the final five-minute presentation and demonstration sequence from the verified run.

Person 3 must not modify consensus code, security rules, Python modules, JavaScript logic, dependency files, or configuration loaders. If a command fails, Person 3 reports the exact command and output rather than improvising a code change.

## 11. Collaboration contract

To keep two developers productive in parallel:

1. During the first hour, Persons 1 and 2 freeze the event envelope, node service methods, configuration fields, and API response shapes.
2. Person 1 returns plain dictionaries from the node service; Person 2 does not depend on `Peer`, `Block`, `Stake`, or wallet implementation details.
3. Person 2 can develop against an in-memory test double located only under tests. Production startup must require a real node service.
4. Each developer works primarily in the owned files listed above.
5. Integration happens at hours 6, 12, and 18 rather than waiting until the end.
6. A failing P0 test blocks P1 work.
7. Any value added as a constant must be classified during review as structural code or moved into validated configuration/runtime data.

## 12. 24-hour schedule

| Time | Person 1 | Person 2 | Person 3 |
|---|---|---|---|
| Hours 0-1 | Freeze interfaces and write PoS test list | Freeze interfaces and sketch API/UI flow | Prepare run log and acceptance checklist |
| Hours 1-5 | Canonical serialization, stake and threshold fixes | Config loader and signalling server | Read current README and identify unclear commands |
| Hours 5-8 | Proof, replay, fork, and double-sign fixes | Signalling client, domain schemas, artifact storage | Run signalling instructions and report results |
| Hours 8-12 | Agent event validation and node service | Permission engine and bounded tools | Prepare user-created demo input and policy through UI when available |
| Hours 12-15 | Persistence isolation and consensus integration tests | Flask APIs and main dashboard | Run first manual happy path and record failures |
| Hours 15-18 | Malicious consensus/event tests | Approval flow, violations, malicious action triggers | Test empty states, form validation, and page refresh behavior |
| Hours 18-21 | Full multi-node integration and fixes | Full multi-node integration and fixes | Execute full acceptance matrix and capture evidence |
| Hours 21-23 | Regression tests and code review for hardcoded data | Regression tests and UI cleanup | Draft demo script and presentation |
| Hours 23-24 | Release candidate only; no new features | Release candidate only; no new features | Final clean run, screenshots, and documentation verification |

## 13. Required tests

### Automated

- Same logical block serializes and hashes identically regardless of dictionary/set insertion order.
- Mutating any consensus field changes the block hash or invalidates the signature.
- Duplicate, missing, unaffordable, or incorrectly signed stakes are rejected.
- Eligibility boundary is identical during production and verification.
- Proof cannot be reused for another seed or creator.
- Omitted stake entries and forged creator stake are rejected.
- Duplicate transactions and duplicate agent event IDs are rejected.
- A completion with an incorrect previous event hash or sequence is rejected.
- Double-signing evidence verifies both conflicting blocks and cannot slash twice.
- Room A never receives Room B peers.
- An existing room manifest cannot be silently replaced, and a node rejects a manifest/genesis mismatch.
- Expired signalling members disappear.
- Missing configuration fails with a useful error rather than a hidden default.
- Unlisted tools and resources are denied.
- Approval-required actions cannot execute before approval.
- Artifact path traversal is rejected.
- Read-only SQL rejects data-changing statements.
- Dashboard APIs return live empty lists when the room has no jobs or blocks beyond genesis.

### Manual

- Start the signalling server with a chosen host, port, TTL, and database path.
- Start at least three nodes using distinct storage directories and no bootstrap address.
- Join all nodes to a room supplied at launch and observe peer discovery.
- Submit an original job and policy through the UI.
- Complete permitted CSV-to-SQL-to-report actions.
- Approve one approval-required action.
- Attempt an unauthorized artifact read and observe denial without execution.
- Replay a completion/event ID and observe rejection.
- Restart a node and verify that its own identity and chain reload without overwriting another node.
- Create a different room and verify that it starts with no peers or application data from the first room.

## 14. Demonstration script

The final demonstration uses values entered at runtime; none are preloaded.

1. Start the signalling service from a supplied configuration.
2. Create a new room in the UI and copy its generated room ID.
3. Launch three nodes with separate storage directories and join that room.
4. Show live discovery and identical chain height.
5. Upload a CSV chosen by the presenter.
6. Create a job and define its policy in the form.
7. Run the worker and show allowed parsing and read-only SQL actions.
8. Show a report-write action waiting for approval, then approve it.
9. Show the signed completion event entering a PoS block.
10. Trigger an unauthorized-read attempt and show its denial and security event.
11. Trigger a replay attempt and show validator rejection.
12. Inspect the blockchain event timeline and content hashes.

## 15. Definition of done

The release is done only when:

- All P0 functionality works from documented commands on a clean run.
- Required automated tests pass.
- The complete manual demonstration has been executed without source edits.
- No production path loads test fixtures or demo state.
- No source code contains runtime identities, ports, peer addresses, room IDs, model configuration, policies, jobs, metrics, rewards, or fake UI data.
- The UI clearly distinguishes proposed, allowed, approved, executed, finalized, denied, and failed states.
- The documentation states what the prototype proves and what it does not prove.
- The system remains useful without an LLM provider: user-submitted jobs can execute deterministic tools under policy and produce signed receipts.

## 16. If time runs short

Cut features in this order:

1. External/local LLM provider.
2. Rewards and reputation.
3. IPFS integration.
4. Server-Sent Events; retain polling.
5. Advanced charts and animations.
6. Additional tools beyond CSV, SQLite, report writing, and hashing.

Do not cut PoS correctness, room isolation, permission enforcement, signatures, replay protection, honest empty states, automated tests, or the malicious-action demonstration.
