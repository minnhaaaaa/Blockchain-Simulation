# AgentGuard Lite: React Product and Interface Specification

## 1. Product intent

The interface is an operational console for a student, evaluator, or developer who needs to see whether distributed agent work was permitted, executed, and finalized correctly. Its primary job is not to market blockchain; it is to make cause and effect inspectable.

The design direction is a **distributed execution flight recorder**: calm, technical, information-dense, and legible. It should feel closer to a network operations instrument than a crypto trading dashboard. Avoid neon gradients, glass cards, coin imagery, fake charts, oversized marketing headlines, and grids of interchangeable KPI cards.

The signature component is the **Execution Rail**: a vertical, hash-linked sequence of job and action events. Each node shows actor, event, policy result, ledger state, and time. A continuous line represents the event-hash chain; a broken/red segment makes an invalid or rejected transition immediately visible.

## 2. Visual system

### Typography

- Interface and headings: IBM Plex Sans Variable, installed in the frontend package and served locally.
- IDs, hashes, timestamps, ports, and code: IBM Plex Mono, served locally.
- Use tabular numerals for metrics and aligned event times.
- Heading hierarchy is compact: page title, section title, label. Do not use display-scale type in the authenticated console.

### Color tokens

| Token | Value | Use |
|---|---|---|
| Graphite | `#14212B` | Primary text, dark navigation |
| Frost | `#EEF2F6` | Application canvas |
| Paper | `#FAFCFE` | Primary working surfaces |
| Protocol Blue | `#3157D5` | Links, focus, active route, submitted/included |
| Verified Teal | `#0D8A7A` | Connected, allowed, finalized, success |
| Alert Vermilion | `#C84B3A` | Denied, violation, invalid, destructive action |

Approval-required uses a patterned/outlined Protocol Blue treatment plus explicit text instead of introducing an ambiguous color. Neutral states use Graphite at reduced opacity. Every state is communicated by text/icon as well as color. Contrast must meet WCAG AA.

### Shape, spacing, and motion

- Two radii only: 4px for compact controls/tags and 10px for major surfaces/drawers.
- One-pixel borders separate information; shadows are reserved for overlays and the inspector drawer.
- Use an 8px spacing base with dense 4px exceptions for labels and table rows.
- Motion is functional: 120–180ms fades/slides for drawers, state changes, and disclosure. Respect `prefers-reduced-motion` and never animate constantly updating numbers.
- Icons come from one library or a small consistent SVG set; icons always have labels or accessible names.

## 3. Application shell

Desktop layout has a 232px left rail, a 56px context bar, a fluid main canvas, and an optional 360px inspector drawer.

```text
┌───────────────┬─────────────────────────────────────────────────┐
│ AgentGuard    │ room / node / provider        sync • identity  │
│ room label    ├─────────────────────────────────────────────────┤
│               │ page title + primary action                    │
│ Overview      │                                                 │
│ Jobs          │ main content                       [inspector]   │
│ Network       │                                                 │
│ Ledger        │                                                 │
│ Security      │                                                 │
│ Settings      │                                                 │
└───────────────┴─────────────────────────────────────────────────┘
```

The left rail contains product name, current room label/short ID, routes, and a leave/switch-room control. The context bar contains connection health, current node label/fingerprint, configured provider state, latest finalized height, and a “last updated” indicator. All values come from APIs.

At widths below 960px, the rail becomes a labelled drawer. At widths below 680px, tables become stacked definition rows, the context bar shows only health and room, and primary actions become full-width. The inspector becomes a full-height modal sheet. No horizontal page scroll is permitted; hashes may truncate visually while retaining copy/full accessible text.

## 4. Route map

| Route | Page job | Primary action |
|---|---|---|
| `/` | Connect to the application API, create a room, or join a room | Create room / Join room |
| `/r/:roomId/overview` | Understand network and work health at a glance | Create job |
| `/r/:roomId/jobs` | Find and filter jobs | Create job |
| `/r/:roomId/jobs/new` | Upload inputs and define an executable permission policy | Submit job |
| `/r/:roomId/jobs/:jobId` | Inspect/operate one job and its signed event chain | Run / Approve / Reject as state permits |
| `/r/:roomId/network` | Inspect discovered peers, connections, stakes, and proposer state | Refresh |
| `/r/:roomId/ledger` | Inspect blocks, finality, and signed events | Inspect block |
| `/r/:roomId/security` | Investigate policy and validation violations | Inspect evidence |
| `/r/:roomId/settings` | View runtime configuration and safe identity summaries | Copy diagnostics |

Unknown rooms/jobs render a contextual 404 inside the shell. Service failures render a retryable error state; they do not redirect to an empty dashboard.

## 5. Room Gateway (`/`)

Purpose: establish runtime origins and room membership without a bootstrap-node assumption.

Layout: split working surface. Left column explains in plain language: “A room defines one blockchain network. Its signed manifest fixes genesis and consensus settings.” Right column contains tabs for Join and Create, with Join selected when a room ID is already supplied by the user.

Content and controls:

- Application API URL field, initialized only from explicit startup config or prior user choice.
- API health check result and request ID on failure.
- Join: room ID, node configuration readiness summary, fetch-and-verify manifest step, then join.
- Create: room ID generator/manual field, consensus fields from the room-manifest schema, genesis allocation editor populated from user input/runtime identity, review of the unsigned manifest, then sign/create.
- “Advanced details” disclosure shows protocol version, public-key fingerprint, and manifest hash.

No default room, host, port, stakes, or consensus values are silently inserted. Required empty fields show explanation and validation. A generated value is displayed and editable/copyable before submission.

## 6. Overview

Top strip uses compact status cells, not oversized cards: service state, connected/discovered peers, height/finalized height, pending approvals, active jobs, violations since the selected time boundary. Counts are live API results.

Main content:

- “Needs attention” queue: pending approvals, rejected submissions, disconnected node, provider unavailable. It disappears into a truthful empty state when clear.
- “Recent execution” abbreviated Execution Rails for the most recently changed jobs.
- “Consensus pulse”: current epoch/seed short form, latest proposer fingerprint, authenticated total stake, and finality lag.
- “Recent blocks”: height, short hash, creator, event count, finality state, time.

Empty copy: “No jobs have been submitted in this room.” with a Create job action. Never generate illustrative jobs or blocks.

## 7. Jobs list and creation

Jobs list is a searchable table with title, state, owner/worker fingerprint, action progress, ledger state, and updated time. Filters: derived job state, ledger state, owner/worker, and text query. Runtime entity options come from results, not fixed arrays beyond structural state enums.

New Job is a three-section form on one route with a persistent review sidebar:

1. **Task**: title, instructions, provider selected from `/api/providers`. Manual proposal mode is displayed only if the backend exposes it as a provider capability.
2. **Inputs**: drag/drop or file picker, per-file upload progress, server-returned artifact ID/hash/size, remove before submit.
3. **Permissions**: rule builder for registered runtime tools, effect, readable artifacts, write scopes, argument constraints, and execution/output limits. Tool options and capabilities come from `GET /api/tools`. A raw policy JSON editor validated against the shared schema is an advanced alternative, never a source of bundled policy data.

The review sidebar shows exactly what the agent may read, write, and execute, policy hash preview, expiry, and validation errors. Submit remains disabled until uploaded artifacts and the complete policy are valid. On success navigate to the job detail and show submitted—not finalized—state.

## 8. Job detail

Header: job title, derived job state, ledger state, short job ID/copy control, owner and accepted worker fingerprints, created/expiry times. Contextual controls appear only when permitted: Accept, Run next action, Approve, Reject, or Download output.

Desktop body has a 2:1 split:

- Left: full Execution Rail grouped by job/action. Selecting a node opens the inspector.
- Right: sticky “Current gate” panel for proposed tool, scoped inputs/writes, matching policy rule, reason, and owner decision controls; followed by artifacts and output summary.

Every Execution Rail node includes event type in human language, exact protocol event name, actor fingerprint, time, sequence, event hash, previous hash, block height if included, and ledger state. Receipt nodes expose request/output hashes, tool version, duration, artifact metadata, and failure data without displaying private contents.

Approval dialog repeats tool, arguments, readable inputs, write scope, and policy reason. It requires an explicit Approve or Reject action; closing makes no decision. Buttons remain disabled during request. Final UI is reconciled from the next server response.

## 9. Network, Ledger, Security, Settings

### Network

Peer table: node name, fingerprint, discovery state, direct connection state, advertised endpoint, last heartbeat, latency if actually measured, and current authenticated stake. A small topology diagram is P1; if present, it uses real peer/connection responses and provides the table as accessible equivalent.

Stake section shows epoch seed short form, total stake, threshold context, latest proposer, and deterministic ordering. Do not display an unexplained probability percentage unless the backend supplies and defines it.

### Ledger

Block table: height, hash, previous hash, creator, timestamp, transaction/event count, finality. Selecting a block opens its complete consensus-relevant summary and linked events in the inspector. A chain-integrity warning has priority over decorative visualization.

### Security

Filterable violation ledger: time, category, reason code, affected job/action, detector fingerprint, evidence hash, inclusion/finality. Detail explains what was rejected and why in plain language, followed by protocol fields. Empty state: “No security violations are recorded for this room.”

### Settings

Read-only runtime overview: application/signalling origins, room/protocol version, safe consensus parameters, node name/fingerprint, storage readiness without absolute sensitive paths, provider readiness, polling interval, frontend version. Actions: copy sanitized diagnostics, switch room, leave room. Never render credentials or private-key material.

## 10. Shared components

- `AppShell`, `SideRail`, `ContextBar`, `MobileNav`
- `ConnectionBadge`, `LedgerStateBadge`, `JobStateBadge`
- `ExecutionRail`, `ExecutionNode`, `HashLink`, `EventInspector`
- `DataTable`, `DefinitionList`, `FilterBar`, `PaginationControls`
- `EmptyState`, `ErrorState`, `Skeleton`, `StaleDataBanner`
- `CopyableId`, `Fingerprint`, `Timestamp`, `HashValue`
- `ArtifactUploader`, `ArtifactList`
- `PolicyBuilder`, `PolicySummary`, `JsonPolicyEditor`
- `ApprovalDialog`, `SubmissionProgress`
- `BlockInspector`, `ViolationInspector`

Components render from props/query data only. Story/test fixtures stay in frontend test directories and cannot be imported by production entry points.

## 11. Data and state rules

- React Router owns URL state; filter/query choices belong in search parameters when shareable.
- TanStack Query owns server state. Do not copy API collections into global React context.
- Local state is limited to unfinished form input, open/closed UI, and transient selection.
- Ajv validation failures become a visible “Incompatible server response” error with request ID and are logged without payload secrets.
- Polling shows stale state after failure and the age of the last successful response.
- Use skeletons only for the initial request; retain data with a subtle refresh indicator thereafter.
- Empty, loading, stale, permission denied, validation error, service unavailable, and not found are distinct states.
- No runtime dataset is bundled. Test fixtures are excluded from the production dependency graph.

## 12. Accessibility and acceptance

- Complete keyboard operation with visible focus and logical order.
- Semantic landmarks, headings, forms, tables, and buttons; no clickable `div` controls.
- Form errors are associated with inputs and summarized at submit.
- Status changes use a polite live region; security/approval interruptions use assertive announcements sparingly.
- Dialog focus is trapped and restored. Tooltips are never the only source of information.
- Hashes and fingerprints have accessible full values and labelled copy feedback.
- At 320px width all required workflows remain possible.
- Playwright covers gateway, create job, policy validation, approval/rejection, finality transition, violation inspection, reconnect/stale behavior, and keyboard navigation of the Execution Rail.
