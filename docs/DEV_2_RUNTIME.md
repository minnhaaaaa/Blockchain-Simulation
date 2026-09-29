# Developer 2 Brief: Signalling, Policy Runtime, and Application API

## Mission

Build the distributed application around the corrected ledger: room discovery, artifacts, policy enforcement, bounded tools, worker/provider orchestration, projections, and the complete HTTP API. This is an equal one-third workstream.

## Read first

Read all of `docs/SCHEMAS.md` and `docs/API_CONTRACT.md`, then `PLAN.md` sections 2, 4–6, 8, 11, 13, and 15 and `TECH_STACK.md` sections 4–13. Treat `contracts/openapi.json` and all JSON Schemas as frozen.

## Deliverables

1. SQLite-backed signalling service and node discovery client with immutable manifests and expiring room-isolated memberships.
2. Artifact store with generated IDs, SHA-256 verification, size bounds, safe paths, and room/job ownership.
3. Deterministic deny-by-default policy evaluator.
4. Registered, bounded P0 tools: artifact text/CSV read, CSV-to-job-SQLite import, read-only SQL, text/JSON report output, artifact hash.
5. Provider interface plus manual provider path; optional configured model adapter only after P0.
6. Worker state machine producing signed proposals, decisions, receipts, results, and violations.
7. Flask application endpoints conforming exactly to `contracts/openapi.json`.
8. Rebuildable job/violation projections and backend integration tests.

## Implementation checklist

- Implement room create/get/join/list/heartbeat/leave. Server assigns membership timestamps, enforces configured TTL/size bounds, removes expired rows, and never mixes rooms.
- Verify manifest signatures before storage and in the discovery client before use. Reject replacement even if the signalling database otherwise accepts writes.
- Make all hosts, ports, database paths, TTLs, roots, limits, origins, provider config, and polling/event options explicit config inputs.
- Store uploaded bytes by generated ID/content digest below a configured root. Normalize paths, reject traversal/symlinks escaping the root, stream and bound uploads, preserve filename only as metadata.
- Compile/evaluate policy rules in the exact order in `docs/SCHEMAS.md`. Validate argument-constraint schemas with bounded complexity. Missing/malformed rules deny.
- Expose tool capability metadata through frozen `GET /api/tools` so the frontend can build/select valid policies.
- Ensure provider output is only a proposed `action.schema.json`; it has no direct tool access.
- Execute registered tools only after allow/approval, with runtime/output bounds and job-specific workspace/database.
- Sign receipts/results, submit events through `NodeService`, and project submitted/included/finalized/rejected distinctly.
- Rebuild job and violation projections from ordered ledger events so SQLite is not an alternate authority.
- Implement every response/error shape in OpenAPI and stable codes in `docs/API_CONTRACT.md`.
- Apply runtime-configured CORS; sanitize logs/errors; never expose credentials, private keys, absolute sensitive paths, artifact bodies, or full prompts in diagnostics.

## Required tests

- Same-room discovery works; room isolation, unknown rooms, expiry, immutable manifest, bad signature, duplicate node update, and leave work correctly.
- Two signalling/application instances do not depend on fixed ports or paths.
- Artifact upload returns correct size/hash; oversize, traversal, cross-room/job access, and tampered bytes fail.
- Policy tests cover no matching rule, explicit deny precedence, allow, approval required, artifacts, write scopes, argument constraints, expiry, and each resource limit.
- Tools reject write SQL, multiple statements, unsafe output paths, unauthorized artifacts, timeout, and oversized output.
- Worker cannot execute before decision; rejection never executes; replayed approval/receipt and invalid job transitions fail.
- Projection rebuilt from the same finalized events is identical.
- Flask tests cover all OpenAPI success/error paths and preserve request IDs.
- End-to-end: create/join room, submit/accept/run job, approve one action, finalize receipt, reject unauthorized read and replay.

## Handoff contract

Consume only Developer 1's `NodeService`, not PoS classes. Provide Developer 3 a running API, OpenAPI-conforming responses, capability/provider endpoints, deterministic test utilities, and clear launch commands. Test fixtures stay below `tests/`; never add a production demo provider or startup seed data.

## Time boxes

- Hours 0–4: signalling schema/database, service skeleton, policy test matrix.
- Hours 4–10: signalling complete, artifacts/policy/tools.
- Hours 10–15: worker/provider/projections and `NodeService` integration.
- Hours 15–20: complete Flask API and frontend integration support.
- Hours 20–24: cross-review Developer 1 validation, e2e/security tests, docs/fixes.

## Done when

Nodes discover peers solely by room ID/configured signalling origin; every action passes the gateway; the API satisfies the frozen contract; all state shown to React comes from live services/ledger projections; and malicious attempts are rejected and observable.
