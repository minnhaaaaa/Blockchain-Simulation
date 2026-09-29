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

- Hours 0–4: tests, canonical representation, defect map.
- Hours 4–10: pseudo-VRF, stake/block/fork/double-sign fixes.
- Hours 10–15: event validation, storage isolation, `NodeService`.
- Hours 15–20: multi-node/malicious integration and Developer 2 integration.
- Hours 20–24: cross-review Developer 2 security paths, full test run, docs/fixes.

## Done when

All regression and integration tests pass repeatedly with dynamic ports/temp directories; nodes converge; malformed, forged, duplicate, replayed, or invalid-transition events are rejected; and Developer 2 can build without importing PoS internals.
