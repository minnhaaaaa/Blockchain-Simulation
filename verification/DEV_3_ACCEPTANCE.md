# Developer 3 Acceptance Matrix

Run timestamp: **2026-09-30 00:24:18 +05:30**

| Check | Result | Evidence |
|---|---|---|
| Schema-derived client generated | PASS | `npm run generate:types` completed from `contracts/openapi.json`. |
| TypeScript, ESLint, RTL/Vitest, production bundle | PASS | `npm run check`; 11/11 tests passed and Vite built. |
| Existing Python suite on Windows | FAIL | 113 passed, 16 failed: SQLite handles remain open during temporary-directory cleanup; one POSIX `0600` assertion observes Windows `0666`. |
| Desktop browser journeys | PASS | 4/4 Playwright Chromium tests. |
| Mobile browser journeys | PASS | 4/4 Pixel 7 Chromium tests. |
| Explicit API origin and health check | PASS | Gateway has no embedded API origin; automated and live checks passed. |
| Create signed room through UI | PASS | Live room `room-cb6839749ec44303bef5` created after preserving canonical PEM text. |
| Join two additional nodes through UI | PASS | Node 2 and Node 3 joined the same signed room. |
| Peer discovery | PASS | Node 3 displayed 2 connected / 2 discovered peers. |
| New room begins empty | PASS | Live overview displayed “No jobs have been submitted in this room.” |
| Refresh introduces no fake data | PASS | Playwright reload retained only API-returned peers; production bundle contains no fixture imports. |
| Upload demo input through UI | PASS | `verification/demo-input.csv` uploaded and received a server artifact ID. |
| Submit uploaded-input job | FAIL | Backend `ArtifactStore.bind()` raises `FileNotFoundError` because the target job directory is absent. |
| Submit job without input | PASS | Job `839541ec-ac2b-478e-8b80-b191f3c9abc0` reached Submitted/Included. |
| Accept job and inspect timeline | PASS | `job.created` and `job.accepted` appeared in the real Execution Rail; finalized height advanced to 1. |
| Manual provider run from browser | FAIL | API returns `manual provider requires an action submitted through the API`; browser lacks the full public key required to construct that action. |
| Approval/rejection UI | PASS (browser fixture) | Real dialog requires explicit decision; desktop/mobile automated journey passed. Blocked for live manual-provider proposal by contract gap. |
| Malicious-action rejection UI | PASS (browser fixture) | Finalized `ARTIFACT_NOT_ALLOWED` violation rendered in Security journey. Live attack path not reachable through current browser contract. |
| Offline and recovery state | PASS | Desktop/mobile API-loss-and-retry journey passed. |
| Responsive layout and keyboard navigation | PASS | Desktop/mobile journeys passed; live room creation/join/job work was keyboard-operated. |
| Claims audit | PASS with flags | See `INTEGRATION_REVIEW.md`; no “secure” or “distributed AI” marketing claim was found in the React UI. |

Browser-test screenshots are stored under `verification/screenshots/`. They use intercepted test-only API fixtures and are intentionally named `browser-test-*`; no fixture enters the production dependency graph.
