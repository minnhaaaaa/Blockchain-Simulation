# Developer 3 Implementation and Demo Runbook

## Delivered

- React 19.3, TypeScript, and Vite application under `frontend/`.
- OpenAPI-generated TypeScript contracts (`npm run generate:types`) with aliases in `src/types/api.ts`; components do not redeclare wire payloads.
- Runtime-selected API origin, normalized error envelopes/request IDs, TanStack Query polling, targeted mutation invalidation, and Ajv validation for manifests and signed event timelines.
- Gateway, overview, jobs, composer, job detail/Execution Rail, approval dialog, network, ledger, security, and settings routes from `FRONTEND_SPEC.md`.
- Responsive navigation, keyboard operation, visible focus, reduced-motion handling, and loading/empty/error/offline/stale states.
- Vitest/React Testing Library and Playwright desktop/mobile coverage.
- Dynamic-port, fresh-identity, three-node demonstration harness in `scripts/demo.mjs`.

No consensus implementation, security rule, Python runtime module, dependency manifest, or configuration loader was changed by Developer 3.

## Installation and verification

From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location frontend
npm ci
npm run check
npx playwright install chromium
npm run test:e2e
```

If `python` is not on `PATH`, create the virtual environment with an explicitly installed Python executable. The demo harness prefers `AGENTGUARD_PYTHON`, then the repository `.venv`, then the platform Python command.

## Repeatable integrated run

```powershell
Set-Location frontend
npm run demo
```

The harness allocates free signalling, API, P2P, and frontend ports; creates three UUID node identities; creates separate storage roots; starts signalling, three node/API processes, and Vite; waits for each health endpoint; and prints the generated UI URL plus `operator-inputs.json`.

In the browser:

1. Open the printed UI URL and choose **Create room**.
2. Use Node 1's printed API URL and paste the generated room ID, protocol, consensus parameters, and three genesis allocations from `operator-inputs.json`.
3. Return to the gateway, use Node 2's API URL, and join the generated room ID.
4. Repeat for Node 3.
5. Open **Network** and confirm two discovered, connected peers.
6. Create a job, optionally upload `verification/demo-input.csv`, select only API-returned provider/tool choices, and enter the policy and limits in the form.
7. Accept the submitted job and inspect the signed Execution Rail and ledger state.
8. Press `Ctrl+C` in the harness terminal to stop the processes.

## Five-minute presentation

- **0:00–0:35 — Trust boundary:** show the gateway and explain explicit API selection, user-entered room parameters, and local signing.
- **0:35–1:20 — Room:** create the room through Node 1, join Nodes 2 and 3, then show both peers as discovered and connected.
- **1:20–2:25 — Policy:** upload the CSV, compose a job, choose a runtime tool, and show deny-by-default rules and execution limits.
- **2:25–3:30 — Ledger:** show the submitted/included job, accept it, and inspect the hash-linked job events and finalized height.
- **3:30–4:20 — Approval/security:** use the Playwright approval journey to show explicit approve/reject behavior and the malicious-action violation evidence view. State clearly that the live manual provider cannot generate proposals through the current browser contract.
- **4:20–5:00 — Evidence and limits:** show the Network, Ledger, Security, and Settings pages, then disclose the open integration failures in `verification/INTEGRATION_REVIEW.md`.
