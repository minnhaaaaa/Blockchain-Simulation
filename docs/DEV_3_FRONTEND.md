# Developer 3 Brief: React Console and System Integration

## Mission

Build the complete React/TypeScript operational console and own cross-system usability/integration evidence. The UI must let an evaluator create/join a room, submit and govern a job, observe consensus/finality, and understand attacks without fake data. This is an equal one-third workstream.

## Read first

Read all of `docs/FRONTEND_SPEC.md`, `docs/API_CONTRACT.md`, and `docs/SCHEMAS.md`; then `PLAN.md` sections 2, 4, 9, and 13–15 and `TECH_STACK.md` sections 2, 4–6, 12, and 14. Treat `contracts/openapi.json` and JSON Schemas as frozen.

## Deliverables

1. Vite React 19.3 TypeScript application with React Router, TanStack Query, Ajv, authored CSS tokens, and locally served IBM Plex fonts.
2. Schema-derived API types/client and runtime validation for high-risk payloads.
3. Every route, page, layout, responsive state, and piece of content in `docs/FRONTEND_SPEC.md`.
4. Complete create/join room and job/policy/artifact flows.
5. Execution Rail, approvals, receipts, blocks, network/stake, and violation inspection.
6. Honest loading/empty/stale/error/unavailable/not-found states with no production fixtures.
7. Vitest/RTL/Playwright coverage and the integrated evaluator demo/runbook.

## Route implementation

- `/`: API connection plus Create Room and Join Room workflows; verify/display manifest details before entering.
- `/r/:roomId/overview`: attention queue, recent execution, consensus pulse, blocks, live status cells.
- `/r/:roomId/jobs`: searchable/filterable accessible jobs table.
- `/r/:roomId/jobs/new`: task, artifact upload, provider selection, policy builder/editor, exact review, submit.
- `/r/:roomId/jobs/:jobId`: header/actions, full Execution Rail, current gate, approval/rejection dialog, artifacts/receipts/results.
- `/r/:roomId/network`: discovered versus connected peers, authenticated stakes, epoch/proposer context.
- `/r/:roomId/ledger`: blocks/finality/events plus block inspector.
- `/r/:roomId/security`: violation filters/list/evidence inspector.
- `/r/:roomId/settings`: safe runtime details, diagnostics copy, switch/leave room.

## Implementation checklist

- Scaffold `frontend/` with strict TypeScript, ESLint, separate `tsc --noEmit`, Vitest/RTL, and Playwright commands. Commit lockfile.
- Generate/derive types from the frozen OpenAPI/JSON Schemas; never maintain parallel hand-written wire types.
- Read application API origin from startup configuration/user gateway input. Do not silently assume localhost or any port.
- Implement a typed fetch layer that parses the error envelope, preserves request IDs, supports cancellation, and validates selected responses with Ajv.
- Define query keys from runtime room/job/action IDs; invalidate targeted queries after mutations. Do not duplicate server collections into context.
- Implement the exact visual tokens/layout in the frontend spec. Keep data surfaces dense and operational; do not convert the product into generic metric cards.
- Build the Execution Rail first as the core reusable visualization. Preserve the distinction between proposed, policy decision, owner decision, executed, included, finalized, denied, rejected, and failed.
- Forms start empty. Provider/tool/artifact/entity choices come from APIs. Structural enum labels may be mapped to friendly text in code.
- Treat a command response as submitted, not finalized; reconcile on polling and surface stale age/retry.
- Hide nothing required for audit: full values are copyable/inspectable, but private keys, credentials, artifact contents, and sensitive paths are never rendered.
- Meet keyboard, focus, semantic, live-region, contrast, reduced-motion, and 320px requirements.
- Own `README` launch/demo instructions with Developer 2 and the final browser acceptance record.

## Required tests

- Unit: wire adapters, query keys, status derivation, ID/hash formatting, event-to-rail mapping, policy form serialization.
- Component: gateway validation, honest empty states, request-ID errors, stale banner, artifact upload, policy errors, approval modal focus/behavior, finalized versus included display.
- Accessibility: keyboard navigation, associated errors/labels, dialog focus restoration, non-color state communication.
- Playwright: connect/create/join; create job with uploaded artifact and policy; accept/run; approve and reject; watch included become finalized; inspect unauthorized-read/replay violations; simulate API loss and recovery.
- Production build contains no fixture imports, embedded peer/job/block arrays, API origins, room IDs, or demo metrics.
- Responsive checks at mobile, tablet, and desktop widths for every primary route.

## Handoff contract

Report contract mismatches with request/response field and operation ID; do not patch around them with `any` or invented fallback data. Coordinate a single contract change with Developers 1 and 2 when necessary. Provide reproducible UI bug steps and request IDs. Cross-review Developer 2's API for safe errors and correct state distinctions.

## Time boxes

- Hours 0–4: scaffold, generated types/client, tokens/shell, gateway.
- Hours 4–10: overview/jobs/create form/artifacts/policy.
- Hours 10–15: job detail, Execution Rail, approval and receipt flows.
- Hours 15–20: network/ledger/security/settings, live API integration, responsive/a11y.
- Hours 20–24: cross-review Developer 1 observability, Playwright demo, production build, README/evidence.

## Done when

Every required operation is usable from the browser; every displayed record comes from the configured API; ledger stages are truthful; attacks and their reasons are understandable; no hardcoded runtime/demo data ships; and automated plus manual acceptance passes at all target widths.
