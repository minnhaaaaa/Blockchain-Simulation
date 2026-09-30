# Certa interface and PDF update — 2026-09-30

## Implemented

- Certa wordmark and page title; removed the shield logo. Existing schema namespaces, package imports and session identifiers remain compatible.
- Supplied monochrome dropdown treatment adapted into one Radix-based control across sign-in, job filters, providers, permissions and action arguments. Portalled menus avoid card clipping; keyboard selection is supported.
- Consistent job-card gaps, wrapping headers, bounded table overflow and full-width mobile filters.
- Real-membership orbital network graph with observed edges only, selection, pointer response, pause, zoom/reset and keyboard controls.
- Cursor-responsive Three.js landing cube, supplied Hyper Text / Word Rotate treatments, and an Animate UI-style CursorProvider/Cursor/CursorFollow adaptation using the existing Motion dependency. No demo image array or fake telemetry.
- Floating dock collapses when idle, reopens on hover/tap, preserves keyboard access, and supports Escape. Reduced-motion changes apply immediately.
- `pdf.read` extracts uploaded PDF text locally in a memory/CPU/time-bounded child process. Page/character cursors make partial coverage explicit. Encrypted, malformed and image-only documents do not produce invented text.
- Compatible models may return a batch despite `parallel_tool_calls: false`; calls are validated then processed sequentially, with policy checks, action-budget enforcement and immediate stops at approval boundaries.

## Verification

The original Certa update passed 154 Python tests, 11 Vitest tests and 4 desktop/mobile Playwright tests. The hosted OpenRouter test was also run explicitly and passed. TypeScript, ESLint and production build passed (build retains advisory bundle-size/runtime-config warnings).

Subsequent fixes add safe Markdown answer rendering, aligned compact attachments and removal of the prompt's leftover shield. Receipt request hashes now use the same canonical UTF-8 encoder as consensus validation; a real-network Unicode report test reproduces the old approval failure and verifies the corrected receipt is accepted by peers. The expanded frontend suite contains 14 unit tests and 6 desktop/mobile browser scenarios. Hosted model calls remain opt-in and are skipped in ordinary regression runs.

- Python regression suite, including PDF pagination, invalid/encrypted files, real signed receipts and batched-call approval/budget tests.
- Frontend TypeScript, ESLint, Vitest and production build.
- Real-network Playwright desktop and mobile journeys: authenticated sign-in, actual uploads/hash computation, approval, download, denial, finality on all peers, logout.
- Additional desktop/mobile checks: automatic dock collapse/reopen, logo removal, orbit movement/pause, keyboard node selection, zoom reset, live reduced-motion preference changes, keyboard dropdown choices and layout bounds across tabs. Screenshots inspected from ignored `frontend/test-results/`.
- Opt-in hosted test **passed against the configured `openrouter/free` endpoint**: a disposable two-page PDF with a randomly generated code was uploaded; the real model requested `pdf.read` and returned the actual code plus text from page two. No personal documents were sent. Hosted availability remains outside the application's control.

## Explicit limitations

- PDF text layer only: scans, handwriting and image/diagram interpretation still require OCR. No paid OCR/model fallback is enabled. Layout-heavy tables may need review. Large documents remain subject to the operator's action/output/context budgets; missing pages must not be represented as read.
- Existing signed jobs do not gain the new PDF permission retroactively; use a new task. Python services need the updated runtime loaded, not only a browser refresh.
- Current demo launcher creates a new room per run. Earlier networks and their saved data were preserved; no room history was reset to demonstrate these changes.
- This remains an educational blockchain simulation, not a production trustless execution guarantee.

The interaction-design guidance informed keyboard/pointer parity, spacing and reduced-motion behavior. The PDF guidance informed local extraction, explicit coverage and rejection of unreadable inputs rather than fabricated results.
