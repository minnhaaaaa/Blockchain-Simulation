# AgentGuard Lite: Frozen Data Contracts

## 1. Authority and scope

The JSON files in `contracts/schemas/` are the machine-readable source of truth for data exchanged between consensus, runtime, API, signalling, and React code. `contracts/openapi.json` is the HTTP source of truth. This document defines semantics that JSON Schema alone cannot express.

The contracts are frozen for the 24-hour implementation. A developer may clarify documentation or add an optional response field only after notifying the other two developers. Renaming a field, changing a type, changing signing bytes, or changing a state transition requires agreement from all three developers and one coordinated contract commit before dependent code changes.

Schema fields, enum members, API paths, and reason-code formats are protocol structure and may be constants. Room IDs, identities, timestamps, hosts, ports, policies, jobs, stake values, content, and displayed records are runtime data and may not be embedded in production code.

## 2. Representation rules

- JSON object keys use `snake_case`; TypeScript may retain those names at the network boundary.
- IDs are lowercase/uppercase-insensitive UUID strings generated at runtime, except `room_id`, which is a user-supplied or securely generated URL-safe identifier.
- Time fields end in `_at_ms` or `_time_ms` and contain UTC Unix epoch milliseconds as integers.
- Hashes are lowercase hexadecimal SHA-256 digests with exactly 64 characters.
- Signatures are standard Base64 strings. The implementation must use one documented ECDSA encoding consistently.
- Public keys are PEM strings at the API boundary. UI summaries display a derived fingerprint, never a private key.
- Unknown object fields are rejected where the schemas specify `additionalProperties: false`.
- Monetary/stake simulation values are non-negative integers. Floating-point values are not used in signed consensus structures.
- Array ordering is meaningful unless a schema and this document explicitly say otherwise.

## 3. Canonical JSON, hashing, and signing

Canonical bytes are UTF-8 JSON produced with sorted object keys, compact separators, Unicode preserved, and non-finite numbers rejected. Python and TypeScript implementations must pass shared cross-language fixtures before integration.

Each signing operation uses a domain prefix so a valid signature for one structure cannot be reused as another:

| Structure | Domain prefix | Fields omitted before signing |
|---|---|---|
| Room manifest | `agentguard.room-manifest.v1` | `signature` |
| Agent event | `agentguard.agent-event.v1` | `event_hash`, `signature` |
| Execution receipt | `agentguard.receipt.v1` | `signature` |
| PoS block/proof | Defined by Developer 1 in the consensus module | Only the specific signature/proof field being produced |

The bytes to sign are `UTF8(domain_prefix + "\n") || canonical_json(unsigned_object)`. `event_hash` is the SHA-256 digest of the Agent Event signing bytes. The signature is then produced over the same bytes. Receipt hashes cover the receipt without its signature. Room-manifest signatures cover the manifest without its signature.

The event validator must recompute `event_hash`, verify `signature` using `actor_public_key`, and validate the payload before inspecting state transitions. A valid signature does not make an invalid transition valid.

## 4. Schema catalogue

| File | Producer | Consumers | Purpose |
|---|---|---|---|
| `common.schema.json` | Contract owners | Everyone | Shared IDs, hashes, artifact references, and API errors |
| `room-manifest.schema.json` | Room creator | Signalling service, every joining node | Immutable signed network definition |
| `room-join.schema.json` | Node | Signalling service | Caller-supplied membership fields |
| `room-member.schema.json` | Signalling service | Nodes and UI | Server-timestamped live membership |
| `room-session-request.schema.json` | React client | Local application/node | Browser-safe create/join inputs; signing stays server-side |
| `policy.schema.json` | Job owner | Gateway and validators | Deny-by-default permissions and limits |
| `job-create-request.schema.json` | React client | Application API | User-authored job fields before IDs/signatures are assigned |
| `job.schema.json` | Job owner/API | Worker, validators, UI | Immutable job request |
| `job-acceptance.schema.json` | Worker | Validators and UI | Worker acceptance event payload |
| `action.schema.json` | Provider/worker | Gateway, validators, UI | Proposed typed tool invocation |
| `decision.schema.json` | Gateway or owner | Worker, validators, UI | Policy/human decision |
| `action-decision-request.schema.json` | React client | Application API | Minimal approve/reject input; actor/hash/time are server-derived |
| `receipt.schema.json` | Tool runner | Validators and UI | Signed execution result |
| `job-result.schema.json` | Worker | Validators and UI | Terminal job summary |
| `security-violation.schema.json` | Gateway/validator | Ledger and UI | Evidence-linked rejected behavior |
| `agent-event.schema.json` | Any authorized actor | Ledger, projection, UI | Signed job event envelope |

## 5. Agent event invariants

- `job.created` is sequence `0`, has `previous_event_hash: null`, and its payload follows `job.schema.json`.
- Every later event uses the next integer sequence and the immediately previous accepted event hash for that job.
- `event_id`, `job_id`, `action_id`, `decision_id`, `receipt_id`, and `violation_id` are globally unique in their respective namespaces.
- Envelope `job_id` equals payload `job_id` whenever the payload contains that field.
- Envelope `room_id` equals the room in the job creation payload.
- `created_at_ms` must be within the configured clock-skew rule and may not precede the preceding event.
- The actor key must be authorized for that transition: owner for creation/human decisions, accepted worker for proposals/receipts/results, gateway or validator for policy decisions/violations.
- An event is visible as submitted before inclusion, included after block inclusion, and finalized only after the room's configured finality depth. The UI must preserve this distinction.

## 6. Job and action state machines

Job states are derived; no mutable `status` field is authoritative.

```text
job.created -> open
open -> job.accepted -> accepted
accepted -> action events -> running | awaiting_approval
accepted | running | awaiting_approval -> job.failed -> failed
accepted | running -> job.completed -> completed
```

Terminal jobs reject every later transition. A job may have only one acceptance in P0. `job.completed` is valid only when every proposed action is in a terminal allowed/denied/rejected state and no approval is pending.

```text
action.proposed
  ├─ action.denied --------------------------------> denied
  ├─ action.rejected ------------------------------> rejected
  ├─ action.allowed -> action.completed ----------> succeeded | failed
  └─ action decision=approval_required -> pending
       ├─ action.approved -> action.completed -----> succeeded | failed
       └─ action.rejected -------------------------> rejected
```

For decision events, the envelope name fixes the permitted `decision` value:

| Event | Required payload decision | Required basis |
|---|---|---|
| `action.allowed` | `allow` | `policy` |
| `action.denied` | `deny` | `policy` or `validator` |
| `action.approval_required` | `approval_required` | `policy` |
| `action.approved` | `approved` | `human` |
| `action.rejected` | `rejected` | `human` |

`action.approval_required` records the policy gate before the later human `action.approved` or `action.rejected` event.

## 7. Policy semantics

Policy evaluation is deterministic and deny-by-default:

1. Reject malformed/expired policies and actions.
2. Select rules whose exact `tool_id` matches the action.
3. If any matching rule has `deny`, deny.
4. If no rule matches, deny with `NO_MATCHING_RULE`.
5. Verify every input artifact is permitted, each requested write target is within a declared scope, and argument constraints pass; otherwise deny.
6. If an applicable rule requires approval, return `approval_required`.
7. Otherwise allow.

`argument_constraints` is a JSON Schema fragment applied to `action.arguments`. The runtime must bound its nesting/size and support only the agreed JSON Schema subset for P0. The policy hash is computed from canonical policy JSON and included in every decision.

## 8. Artifact invariants

- The server creates `artifact_id`; the uploaded filename is metadata, not a storage path.
- Stored bytes must hash to the declared `sha256` and have the declared `size_bytes`.
- Artifact ownership and room/job scope are checked on every read.
- Ledger events contain artifact metadata and hashes, not file contents.
- Output artifacts are first written to a temporary job-scoped location, verified, and atomically promoted.
- A receipt `request_hash` covers the canonical action proposal; `output_hash` covers the ordered output artifact references and any structured non-file result.

## 9. Room invariants

- A room manifest is immutable once stored for a `room_id`.
- A joining node verifies manifest signature, protocol version, genesis descriptor, and consensus parameters before connecting.
- The signalling service supplies `joined_at_ms` and `last_heartbeat_ms`; callers cannot choose them.
- Membership expires according to server configuration, not a client-provided TTL.
- A member list never includes expired members or members from another room.
- Discovery metadata is not identity proof; the P2P key handshake must match the advertised fingerprint.

## 10. Versioning and generated types

Every persisted signed object contains `schema_version: 1`. The React client generates or derives types from `contracts/openapi.json` and the referenced schemas; it does not maintain hand-written duplicate interfaces. Python validation targets the same files. Generated files must be reproducible and may be committed, but the schema remains authoritative.

Breaking changes require schema version 2 and migration/compatibility rules. Silently accepting a new field in a signed version-1 object is prohibited because it can create different hashes across nodes.

## 11. Validation order

Receivers validate in this order: request-size bound, JSON parse, schema, canonical-hash match, signature, identity/authorization, temporal checks, duplicate/replay checks, state transition, policy/consensus rule, persistence. Failures return or record a stable reason code and must never partially apply state.
