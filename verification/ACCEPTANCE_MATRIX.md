# Manual Acceptance Matrix

Executed/assessed: 2026-09-29 21:39:58 +05:30  
Overall: **0 passed, 10 failed (all blocked by missing implementation/startup prerequisites)**

| # | Acceptance requirement from `PLAN.md` | Timestamp | Result | Evidence / blocker |
|---:|---|---|---|---|
| 1 | Start signalling server with chosen host, port, TTL, and database path | 2026-09-29 21:39:58 +05:30 | FAIL | No signalling source or launch command exists. |
| 2 | Start at least three nodes with distinct storage directories and no bootstrap address | 2026-09-29 21:39:58 +05:30 | FAIL | No AgentGuard node launcher/configuration exists; Python is unavailable. |
| 3 | Join all nodes to a launch-supplied room and observe peer discovery | 2026-09-29 21:39:58 +05:30 | FAIL | No room/signalling implementation or UI exists. |
| 4 | Submit an original job and policy through the UI | 2026-09-29 21:39:58 +05:30 | FAIL | No dashboard/frontend exists. |
| 5 | Complete permitted CSV-to-SQL-to-report actions | 2026-09-29 21:39:58 +05:30 | FAIL | No AgentGuard tools/runtime exists. |
| 6 | Approve one approval-required action | 2026-09-29 21:39:58 +05:30 | FAIL | No approval UI/API/runtime exists. |
| 7 | Attempt unauthorized artifact read and observe denial without execution | 2026-09-29 21:39:58 +05:30 | FAIL | No policy gateway, artifact service, or UI exists. |
| 8 | Replay a completion/event ID and observe rejection | 2026-09-29 21:39:58 +05:30 | FAIL | No AgentGuard event API or documented malicious action exists. |
| 9 | Restart a node and verify isolated identity/chain reload | 2026-09-29 21:39:58 +05:30 | FAIL | Required node service cannot start. Legacy storage is consensus-scoped, not per configured node directory. |
| 10 | Create a different room and verify it starts without peers/application data from room one | 2026-09-29 21:39:58 +05:30 | FAIL | No room or dashboard implementation exists. |

## Additional Person 3 checks

| Check | Result | Evidence |
|---|---|---|
| Refresh does not introduce fake data | FAIL | Cannot test: no page/dashboard exists. |
| New room begins empty | FAIL | Cannot test: no room creation implementation exists. |
| Room ID created through real UI | FAIL | No UI exists. |
| Node names created through real UI | FAIL | No UI exists; legacy peer takes terminal input. |
| Job text and policy created through real UI | FAIL | No UI exists. |
| Demo input uploaded through real UI | FAIL | No UI/upload endpoint exists. |
| Required screenshots captured | FAIL | The required application states cannot be produced. See `evidence/README.md`. |

No source workaround was attempted. These failures must be returned to Persons 1 and 2 for implementation or documentation correction.

