# Manual Acceptance Matrix

Historical result from the teammate's Windows run at commit `144ae83`. See `INTEGRATION_REVIEW.md` for the merged revision. These rows are not a current acceptance result.

Initially assessed: 2026-09-29 21:39:58 +05:30

Re-verified against `origin/main` `144ae83`: 2026-09-29 21:56:37 +05:30

Overall: **0 passed, 10 failed (all blocked by missing implementation/startup prerequisites)**

| # | Acceptance requirement from `PLAN.md` | Timestamp | Result | Evidence / blocker |
|---:|---|---|---|---|
| 1 | Start signalling server with chosen host, port, TTL, and database path | 2026-09-29 21:56:37 +05:30 | FAIL | Runtime config was supplied and the documented command was attempted; `python` is unavailable. |
| 2 | Start at least three nodes with distinct storage directories and no bootstrap address | 2026-09-29 21:56:37 +05:30 | FAIL | No composed AgentGuard node launcher or real node adapter command exists; Python is unavailable. |
| 3 | Join all nodes to a launch-supplied room and observe peer discovery | 2026-09-29 21:56:37 +05:30 | FAIL | Backend room components exist, but the required node integration and UI do not. |
| 4 | Submit an original job and policy through the UI | 2026-09-29 21:56:37 +05:30 | FAIL | No dashboard/frontend exists. |
| 5 | Complete permitted CSV-to-SQL-to-report actions | 2026-09-29 21:56:37 +05:30 | FAIL | Backend tools exist but cannot be started or exercised through the required UI. |
| 6 | Approve one approval-required action | 2026-09-29 21:56:37 +05:30 | FAIL | Backend route/runtime code exists, but there is no runnable composed app or approval UI. |
| 7 | Attempt unauthorized artifact read and observe denial without execution | 2026-09-29 21:56:37 +05:30 | FAIL | Backend policy code exists, but the required real UI/integrated run is unavailable. |
| 8 | Replay a completion/event ID and observe rejection | 2026-09-29 21:56:37 +05:30 | FAIL | Backend tests claim coverage but cannot run; no integrated malicious-action UI exists. |
| 9 | Restart a node and verify isolated identity/chain reload | 2026-09-29 21:56:37 +05:30 | FAIL | Real node adapter/composed node startup is not delivered. |
| 10 | Create a different room and verify it starts without peers/application data from room one | 2026-09-29 21:56:37 +05:30 | FAIL | No dashboard exists and signalling could not start without Python. |

## Additional Person 3 checks

| Check | Result | Evidence |
|---|---|---|
| Refresh does not introduce fake data | FAIL | Cannot test: no page/dashboard exists. |
| New room begins empty | FAIL | Cannot test: no room-creation UI or runnable composed application exists. |
| Room ID created through real UI | FAIL | No UI exists. |
| Node names created through real UI | FAIL | No UI exists; legacy peer takes terminal input. |
| Job text and policy created through real UI | FAIL | No UI exists. |
| Demo input uploaded through real UI | FAIL | No UI exists; backend upload behavior is not a substitute for the required UI test. |
| Required screenshots captured | FAIL | The required application states cannot be produced. See `evidence/README.md`. |

No source workaround was attempted. These failures must be returned to Persons 1 and 2 for implementation or documentation correction.
