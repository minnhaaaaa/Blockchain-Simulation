# Live demo verification — 2026-09-30

Verified on Linux, on `codex/live-demo-redesign`. This supersedes the original fixture-backed frontend acceptance report.

| Check | Result |
| --- | --- |
| Complete Python suite | 133 passed |
| TypeScript project build | Passed |
| ESLint | Passed |
| Frontend unit tests | 11 passed |
| Vite production build | Passed; bundle-size advisory and intentional external runtime-config script warning remain |
| Desktop live browser journey | Passed |
| Pixel 7 live browser journey | Passed, including no horizontal page overflow and working floating dock |
| Private API without a session / incorrect access key | Rejected |
| Public runtime configuration | No node access keys exposed |
| Real multi-file uploads → job creation | Passed |
| Manual signed proposal → approval → execution | Passed |
| Downloaded hash result | Matches locally calculated SHA-256 of freshly generated input bytes |
| Denied report action | Real signed violation, visible in Security |
| Job completion/finality | Verified through authenticated HTTP on all three actual P2P nodes |
| Quiet network finality | Real empty successor blocks propagate and finalize the last event |
| CSV → SQLite → SQL → reviewed report | Actual uploaded values summed correctly; report downloaded and compared |
| Raw policy mode | Validates independently of empty builder fields; invalid policies rejected |
| Atomic artifact binding | Failure rolls back all associations without moving/deleting input bytes |

Browser tests do not use `page.route`, response interception, canned network fixtures, a fake node service, or a mock provider. The isolated test harness generates its inputs and identities and supplies test resource settings; production launch settings are operator-supplied instead. Screenshots under `frontend/test-results/` are captures of these actual runs, not illustrative dashboard data.

The complete runbook is [docs/LIVE_DEMO.md](../docs/LIVE_DEMO.md). The current execution provider is explicitly manual. Autonomous LLM planning, private cross-node file transfer, public deployment security, and a Windows rerun are not claimed by this verification.

Design uses pale canvas/forest accents and deliberate typography informed by the supplied reference repositories. GSAP React hooks scope and clean up entrance/dock animation; reduced-motion users receive a static presentation. The landing-page permission diagram is clearly explanatory, not telemetry.
