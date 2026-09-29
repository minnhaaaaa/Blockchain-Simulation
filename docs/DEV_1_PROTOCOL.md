# Developer 1 Brief: Protocol, PoS, and Ledger Boundary

## Mission

Make the blockchain trustworthy enough to carry AgentGuard events. You own consensus correctness, canonical signed data at the ledger boundary, node-isolated persistence, and the read/write adapter consumed by Developer 2. This is an equal one-third workstream.

## Read first

Read `PLAN.md` sections 2, 5, 7, 8, 13, and 15; `TECH_STACK.md` sections 5–10 and 13–15; `docs/SCHEMAS.md`; and the `NodeService` section of `docs/API_CONTRACT.md`. Treat `contracts/schemas/agent-event.schema.json` and `room-manifest.schema.json` as frozen.

## Deliverables

1. Failing regression tests for every known PoS defect before changing the implementation.
2. One canonical JSON/hash/signature implementation used by stakes, blocks, room manifests, and agent events where their domain rules apply.
3. Correct deterministic pseudo-VRF eligibility and proof verification.
4. Complete, immutable, deterministic stake snapshots and authenticated fork selection.
5. Correct duplicate/replay and double-signing validation.
6. Namespaced per-room/per-node persistence.
7. A `NodeService` adapter implementing the exact methods in `docs/API_CONTRACT.md`.
8. Unit, async integration, and three-node consensus tests, including malicious cases.

## Implementation checklist

- Inventory `shared_blockchain_structures.py`, `consensus/pos/blockchain_structures.py`, `consensus/pos/p2p.py`, and `consensus/pos/mal_node.py`; remove duplicated validation paths or route them through shared pure functions.
- Define consensus-domain canonical representations. Block signing/hash bytes must include previous hash, ordered transactions/events, files/artifact references, creator, declared stake, full ordered stake snapshot, epoch seed, proof, timestamp, block ID, and every finality/slash field that changes validity.
- Make pseudo-VRF proof deterministic for `(private_key, epoch_seed)` and verify against the creator public key and exact seed before threshold comparison. Use the same strictly-less-than boundary in production and validation.
- Validate unique staker identity, positive/affordable stake, signature, deterministic ordering, nonzero total, and creator stake equality.
- Reject duplicate transaction/event IDs across accepted history and the candidate block, not only within one list.
- Define deterministic fork score/tie-break using authenticated fields only.
- Validate double signing as same creator/height/seed, different signed block hashes, both signatures valid; apply evidence once.
- Validate `agent-event.schema.json`, canonical hash, signature, sequence, previous hash, actor authorization, and state transition before mempool acceptance.
- Ensure malicious-node code can construct attacks but cannot weaken the honest validator path.
- Derive storage below configured `<data-root>/<room-id>/<node-id>/`; fail if required configuration is absent.
- Return serializable copies from `NodeService`; never expose mutable chain internals to Flask/runtime code.

## Incoming `security-fixes` branch merge gate

Developer 1 owns the integration of `origin/security-fixes`. The reviewed baseline is commit `0327e13`. The branch contains useful hardening across PoW, PoS, PoA, networking, IPFS, and the contract sandbox, but it must not be merged unchanged. Preserve fixes that pass tests, correct the following blockers on the integration branch, and merge only after the complete gate passes.

### Required consensus corrections

1. **Remove PoS proof grinding.** Replace randomized `private_key.sign(seed)` pseudo-VRF generation with a deterministic proof for the exact `(validator key, domain-separated epoch seed)` input. Repeated calls with the same input must produce identical proof and output. Document that this remains an educational deterministic pseudo-VRF unless a standards-based VRF is introduced.
2. **Bind the proof to the block.** Include the proof, seed, complete stake snapshot, and every other consensus-relevant field in canonical block hashing and signing. Changing any one of them must change the block hash and invalidate the creator signature.
3. **Require a complete authenticated epoch stake snapshot.** Live block validation must require exact equality between the block snapshot and the locally authenticated snapshot—not merely reject snapshots whose total is larger. Chain synchronization must validate snapshot completeness from authenticated ledger/epoch state, not trust whichever signed stakes the creator chose to include.
4. **Use one eligibility boundary.** Block production, live verification, and full-chain verification must all accept only `vrf_output < threshold`. Put the calculation in one shared pure function so the three paths cannot drift.
5. **Repair double-sign detection.** Evidence is slashable only when two blocks have the same creator, height, and epoch seed; different signed block hashes; and two valid creator signatures. Same-creator divergence must enter the evidence path. Different creators winning the same epoch is a normal fork, not double signing. Evidence is idempotent and cannot slash twice.
6. **Repair block equivalence.** Correct comparisons such as `self.creator == self.creator`, eliminate unused comparison variables, and define equality from the canonical signed block identity. Add negative tests for different creator, seed, proof, snapshot, transaction ordering, and hash.
7. **Authenticate PoA authority-set evolution.** A block signer must not be able to replace `miners_list` merely by placing a new list in a signed block. Every authority-set transition must reference a valid administrator-signed update, activate at its declared height, and be replay-protected. Full-chain validation must reconstruct the authority set from genesis plus those updates before accepting each block.
8. **Make genesis a room trust anchor.** A node without a local chain must accept only the genesis descriptor/hash from the verified room manifest. “First valid self-signed genesis received” is not sufficient. Existing-chain comparison remains a defense, not the root of trust.
9. **Canonicalize every signed representation.** Replace ordinary `json.dumps()`/`str(object)` consensus signing with the canonical encoding defined in `docs/SCHEMAS.md`. Dictionary insertion order, peer relay, or deserialize/reserialize cycles must not change bytes.
10. **Decide signature compatibility explicitly.** The SHA-256 upgrade invalidates previously stored SHA-1 signatures. Either implement a versioned, tested migration/verification rule or intentionally require a clean network and make startup reject legacy storage with a precise message. Never silently mix both signature domains in one room.
11. **Preserve validated branch hardening.** Keep the corrected transaction signer binding, positive-amount checks, PoW miner hashing, genesis/duplicate checks, malformed-signature handling, bounded peer/message collections, RestrictedPython guards, worker cleanup, and IPFS argument/time bounds unless a regression test proves a safer replacement is needed.

### Mandatory branch regression tests

- Calling the pseudo-VRF repeatedly for one key/seed yields one proof/output; attempts to grind alternate valid proofs fail.
- Mutating proof, seed, one stake entry, creator stake, files, transactions, creator, timestamp, or block ID invalidates hash/signature.
- A creator omitting any authenticated epoch staker is rejected during live validation and chain sync.
- Producer, live validator, and chain validator return the same result for outputs immediately below, equal to, and above the threshold.
- Same creator/height/seed with different signed hashes slashes once; different creators, heights, seeds, identical hashes, or either invalid signature never slash.
- Block equivalence detects every consensus-relevant difference.
- An authorized PoA miner cannot add itself or another node to the next authority set without a valid administrator-signed transition.
- A new node rejects a validly self-signed chain whose genesis differs from the verified room manifest.
- Canonical bytes and hashes remain identical after serialize/deserialize and across different dictionary insertion orders.
- Legacy SHA-1 state follows the selected migration policy: successfully migrated under an explicit version, or rejected before networking begins.
- Existing branch tests cover wrong-key spending, negative amounts, rewritten PoW miner, replayed transactions, duplicate in-block transactions/stakes, malformed network messages, sandbox escape attempts, timeout cleanup, and unsafe IPFS arguments.

### Merge procedure and acceptance

1. Create an integration branch from current `main`; merge or rebase `origin/security-fixes` into it. Do not force-push or replace `main` with the teammate branch because it diverged before the frozen contracts commit.
2. Separate mechanical branch import from follow-up consensus corrections when practical so review can identify which teammate changes were retained or modified.
3. Run syntax checks, all consensus unit tests, all branch regression tests, and the three-node dynamic-port integration suite from clean temporary storage.
4. Run one clean-room network and one explicit legacy-storage compatibility test according to the chosen migration policy.
5. Request review from Developer 2 for networking/configuration effects and Developer 3 for ledger states that the API/UI must display.
6. Merge only when no P0/P1 consensus finding remains, every required test passes repeatedly, and the pull request explains any claimed security fix that was dropped or redesigned.

The branch is **not merge-ready** if it has no automated tests, accepts incomplete stake snapshots, permits randomized-proof grinding, treats same-creator forks as non-malicious, permits unauthenticated PoA authority changes, or silently invalidates persisted networks.

## Required tests

- Same seed/key produces identical proof/output; changed seed/key changes it; invalid proof fails.
- Eligibility producer and verifier agree at threshold edge.
- Reordered/mutated consensus field changes the block hash or fails canonical validation.
- Duplicate stake identity, forged stake, zero total, mismatched creator stake, and reordered snapshot fail.
- Duplicate event, ID reuse with changed bytes, skipped/repeated sequence, wrong previous hash, stale event, and replayed receipt fail.
- Fork choice is stable regardless of peer arrival/order.
- Valid double-sign evidence applies once; mismatched height/seed/creator or invalid signature does not slash.
- Three dynamically ported nodes converge from the same signed manifest.
- Separate nodes cannot overwrite identities/chains.
- An invalid event submitted through `NodeService` never reaches accepted state.

## Handoff contract

Give Developer 2 a working in-process `NodeService` plus test factory; give Developer 3 conforming JSON examples generated inside tests, never a production mock dataset. Notify both developers immediately if a frozen schema cannot express necessary ledger state. Do not change HTTP routes or frontend types directly.

## Time boxes

- Hours 0–4: import/review `security-fixes`, write branch regression tests, canonical representation, defect map.
- Hours 4–10: pseudo-VRF, stake/block/fork/double-sign and PoA authority-transition fixes.
- Hours 10–15: event validation, storage isolation, `NodeService`.
- Hours 15–20: multi-node/malicious integration and Developer 2 integration.
- Hours 20–24: cross-review Developer 2 security paths, full test run, docs/fixes.

## Done when

All regression and integration tests pass repeatedly with dynamic ports/temp directories; nodes converge; malformed, forged, duplicate, replayed, or invalid-transition events are rejected; and Developer 2 can build without importing PoS internals.
