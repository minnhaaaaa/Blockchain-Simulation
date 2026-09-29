# Five-Minute Presentation and Demo Runbook

Current release status: **NO-GO for a live AgentGuard demo.** This sequence is the presentation that can be made truthfully from the verified run. The intended live steps remain gated until the implementation exists and the acceptance matrix passes.

## 0:00-0:40 — Scope

Explain that AgentGuard Lite is a planned local, multi-node Proof-of-Stake prototype for policy-controlled agent tasks. State clearly that it is not production isolation, verified AI correctness, private distributed inference, or a cryptocurrency.

## 0:40-1:30 — What was inspected

Show the repository tree and the frozen `PLAN.md`/`TECH_STACK.md`. Explain the Person 3 guardrail: verification did not alter consensus, security, runtime, frontend, dependency, or configuration code.

## 1:30-2:30 — Clean-run evidence

Show `COMMAND_LOG.md`:

1. The exact clone command succeeds.
2. The documented `cd BlockChain_Prototype` fails because the clone is named `Blockchain-Simulation`.
3. Python/pip commands fail on this host.
4. No signalling, AgentGuard node, dashboard, or test command exists.

## 2:30-3:30 — Acceptance outcome

Show `ACCEPTANCE_MATRIX.md`: all ten manual scenarios fail because the required implementation cannot be started. Emphasize that UI data and screenshots were not fabricated and source was not edited to simulate a pass.

## 3:30-4:20 — Claim safety

Show `CLAIMS_AUDIT.md`. Call out the absent web interface, the unsupported “functional” test claim, and the need to describe the contract executor as educational/restricted rather than a production security sandbox.

## 4:20-5:00 — Release gates and next run

List the re-test gates from `PERSON_3_REPORT.md`. End with the intended verified sequence once those gates pass: create a fresh room in the UI, launch three isolated nodes, show discovered peers, submit user-entered CSV/job/policy, approve one action, display a finalized receipt, reject unauthorized access and replay, refresh without fake data, then create a second empty room.

## Intended runtime values for the future verified run

These are operator-entered examples, not production defaults or source constants:

- Node labels: `validator-saffron`, `worker-indigo`, `auditor-jade`
- Job: “Import the uploaded expense CSV into the job database and produce a category-total JSON report.”
- Allowed path: read the uploaded artifact, parse CSV, import rows, execute read-only aggregation SQL, write the JSON report, hash the output.
- Approval-required action: writing the final report.
- Malicious attempts: read an artifact not granted by the policy; replay a previously submitted completion event ID.

Generate the room ID in the UI at runtime. Do not place any of these values into application source or startup fixtures.

