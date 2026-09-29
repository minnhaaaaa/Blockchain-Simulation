# AgentGuard Lite: API and Service Contract

## 1. Source of truth

`contracts/openapi.json` defines HTTP request and response shapes. `contracts/schemas/` defines signed and shared objects. This document defines endpoint behavior, errors, finality, and the in-process node boundary.

There are two independently configured HTTP origins:

- Signalling origin: `/health` and `/api/rooms/**`.
- Application origin: `/health`, `/api/room-session`, `/api/status`, `/api/providers`, `/api/tools`, `/api/peers`, `/api/chain`, `/api/stakes`, `/api/artifacts`, `/api/jobs/**`, and `/api/violations`.

Neither origin is compiled into the React bundle. A startup-supplied config document or an explicit user connection form provides the application origin. The node receives the signalling origin through its launch configuration.

## 2. HTTP rules

- JSON responses use `application/json`; uploads use `multipart/form-data`.
- Resource creation returns `201`; asynchronous ledger commands return `202`; reads/synchronous commands return `200`; successful empty mutations return `204`.
- All errors use `common.schema.json#/$defs/apiError` and include a runtime-generated `request_id`.
- Unknown fields, invalid formats, and contract violations return `422`.
- Missing resources return `404`; immutable/duplicate or invalid-state writes return `409`.
- Requests beyond configured bounds return `413`.
- A healthy API whose node dependency is unavailable returns `503` for dependent operations.
- Secrets and private keys never appear in bodies, errors, or logs.
- GET results reflect the latest local projection and include ledger-state fields where applicable; they do not claim finality merely because a command returned successfully.

## 3. Idempotency and commands

Room creation is idempotent only when the same `room_id` and byte-equivalent signed manifest already exist; a different manifest returns `409 ROOM_ALREADY_EXISTS`. Joining replaces the same node's advertised membership after the fingerprint is verified. Heartbeat and leave are idempotent from the caller's perspective.

Signed submissions use their IDs as idempotency keys. Repeating the exact same accepted signed object returns the existing submission reference. Reusing an ID with different content returns `409 ID_REUSE`. Approval/rejection and job acceptance are one-way state transitions and return `409 INVALID_TRANSITION` when repeated incompatibly.

Command responses return a submission object containing runtime-generated `submission_id`, `event_id`, and `ledger_state`. Initial state is normally `submitted`; it may be `included` only if inclusion completed synchronously. The browser polls the job or chain until `finalized` or `rejected`.

## 4. Signalling behavior

`POST /api/rooms` validates the manifest, verifies its creator signature, stores it once, and returns the exact stored object. It does not generate the room, consensus values, or genesis data.

`POST /api/rooms/{room_id}/members` accepts `room-join.schema.json`, verifies the path matches an existing room, assigns server timestamps, and returns `room-member.schema.json`. The node must omit itself when choosing peers.

`GET /api/rooms/{room_id}/members` returns only non-expired members from that room plus `server_time_ms`. Heartbeat updates only the matching `(room_id, node_id)` membership. Leave removes only that membership.

## 5. Application behavior

`POST /api/room-session` is the browser-safe room operation. For create, the browser supplies the reviewed consensus/genesis inputs and the local node generates IDs/timestamps, signs the manifest, stores it through signalling, and joins. For join, the browser supplies only a room ID; the node fetches and verifies the manifest before joining. Private keys never enter the browser.

`GET /api/status` is the first React query. It reports node/room identity, service readiness, chain height, peer count, provider readiness, and server time. A missing provider is a valid `unconfigured` state, not fabricated readiness.

`GET /api/providers` lists only runtime-configured providers and their readiness. An empty list is valid.

`GET /api/tools` lists the actual registered tool IDs, descriptions, versions, argument schemas, and possible output kinds used to construct policies.

`GET /api/peers`, `/api/chain`, and `/api/stakes` are read models derived from authenticated node state. Peer discovery and direct connection are distinct fields. Chain responses identify finalized height separately from current height.

`POST /api/artifacts` streams a bounded upload, computes its digest, stores it under a generated ID, and returns an artifact reference. It never trusts the filename as a path.

`POST /api/jobs` accepts a complete schema-valid job created from user input and prior artifact references. Server-side ownership, policy hash, expiry, and event rules are validated before its `job.created` event is submitted.

`GET /api/jobs` filters by documented query parameters and returns projection summaries. `GET /api/jobs/{job_id}` returns the job, derived state, ordered event timeline, actions, decisions, receipts, and current ledger state.

`POST /api/jobs/{job_id}/accept` identifies the authenticated/runtime worker and submits a `job.accepted` event. `POST .../run` asks the configured provider to propose the next action; it does not bypass policy or directly execute a tool.

`POST .../actions` supports a manual or provider-produced proposal. The gateway records the proposal, evaluates policy, records the decision, and executes only when allowed/approved. `POST .../decision` accepts only `approved` or `rejected` from the job owner for a currently pending action.

`GET /api/violations` returns evidence summaries visible to the current room. It never returns secret request headers, credentials, raw private artifacts, or private keys.

## 6. Stable error codes

Implementations may add codes but must support these shared codes:

| Code | Status | Meaning |
|---|---:|---|
| `VALIDATION_FAILED` | 422 | Body/query/path violates the frozen contract |
| `ROOM_NOT_FOUND` | 404 | No such room manifest |
| `ROOM_ALREADY_EXISTS` | 409 | Room ID is bound to another manifest |
| `RESOURCE_NOT_FOUND` | 404 | Job, action, artifact, or node is absent |
| `INVALID_SIGNATURE` | 422 | Signature does not verify for canonical bytes |
| `HASH_MISMATCH` | 422 | Declared hash differs from recomputed hash |
| `ID_REUSE` | 409 | Existing ID is attached to different bytes |
| `INVALID_TRANSITION` | 409 | Command is incompatible with current derived state |
| `POLICY_DENIED` | 409 | Requested action is forbidden |
| `APPROVAL_REQUIRED` | 409 | Execution cannot continue without owner action |
| `REPLAY_DETECTED` | 409 | Event/receipt/sequence has already been consumed |
| `PROVIDER_NOT_CONFIGURED` | 409 | Run was requested without a provider |
| `NODE_UNAVAILABLE` | 503 | Application cannot reach its configured node |
| `PAYLOAD_TOO_LARGE` | 413 | Configured request/upload bound exceeded |
| `INTERNAL_ERROR` | 500 | Sanitized unexpected failure |

## 7. Node service boundary

The Flask application and AgentGuard runtime depend on a narrow Python interface; they must not import or mutate PoS internals:

```python
class NodeService(Protocol):
    def submit_event(self, event: dict) -> Submission: ...
    def get_event(self, event_id: str) -> dict | None: ...
    def list_job_events(self, job_id: str) -> list[dict]: ...
    def get_chain_summary(self, limit: int) -> dict: ...
    def get_peer_summaries(self) -> list[dict]: ...
    def get_stake_snapshot(self) -> dict: ...
    def subscribe_state_changes(self, callback: Callable[[dict], None]) -> Cancel: ...
```

`submit_event` performs full validation or returns a typed rejection; it never returns success for a merely queued invalid object. Read methods return copies/serializable projections. P0 may implement `subscribe_state_changes` with an internal callback feeding projection invalidation; React uses polling and does not call this interface directly.

## 8. Browser query behavior

TanStack Query keys are derived from runtime IDs: status, providers, peers by room, chain by room/limit, stakes by room, jobs by room/filter, job by room/job ID, and violations by room/filter. Mutations invalidate only related keys. Poll intervals come from runtime UI configuration and pause when the tab is hidden where safe.

The client treats network errors, API rejection, inclusion, and finality as separate states. It may optimistically disable a button but must not display “finalized” before the server does. Ajv validates high-risk API objects—room manifest, job detail, decisions, and receipts—before rendering them.

## 9. Security and observability

Every request receives a request ID and structured log entry. Logs include operation, result, duration, resource IDs, and reason code; they exclude private keys, credentials, document bodies, and full prompts. State-changing operations record the authenticated actor fingerprint. CORS accepts only runtime-configured origins. Browser output is escaped, and artifact downloads use safe content disposition.
