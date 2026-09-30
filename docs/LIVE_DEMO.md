# Live demo: your inputs, real execution

## What runs

The launcher starts a real signalling service, the number of PoS nodes you configure, authenticated HTTP APIs, and the React application. Nodes create/join one generated room through signalling, then exchange signed events and blocks over P2P sockets. The dashboard polls these APIs; it has no fixture fallback or generated activity feed.

There are two execution paths: **prompt-first AI tasks** through your OpenAI-compatible Chat Completions endpoint, and **manual proposals** under Advanced setup. Both use the same real tools, signed policies, approval checks and receipts. There is no canned model response or fallback agent. An unconfigured agent stays unavailable.

## Connect your AI agent

Copy `agent-provider.example.json` to `agent-provider.local.json` in the repository root (a blank local file may already exist). Fill in `base_url`, `model` and `api_key`. The base URL is your provider's API base, including its version path if needed, **without** `/chat/completions`. Use the exact tool-capable model ID supplied by your provider. HTTPS is required except for loopback endpoints. The file is gitignored and read only by Python, never bundled into Vite or returned by the API. Restrict it to your account with `chmod 600 agent-provider.local.json`.

The numeric values in the example are editable resource limits, not network records or sample results. `job_limits` controls the policy signed for each new prompt task. `max_context_bytes` bounds the complete model request: oversized histories fail explicitly rather than silently dropping data. `max_response_bytes` and `timeout_seconds` bound upstream responses. Changing these settings requires no restart; check settings again in the prompt view. The `ready` provider state means configuration is present, **not** that upstream credentials have been verified. The first requested run verifies upstream access.

Start the launcher, sign in, choose **Create job**, enter your prompt and optionally attach files, then press **Run task**. The server generates the task title from your prompt and a policy from the actual tool registry: reads of attached files are allowed; declared writes require approval. The model receives real tool results and continues until it answers, needs approval, reaches a limit, or errors. After reviewing a write, use **Continue agent**. Advanced setup still offers custom allow/deny/approval rules and manual execution.

Your prompt, file metadata and permitted tool results are sent to your selected AI provider. Raw uploads are not automatically included in its context, but reading a file with a tool sends its contents as a tool result. Instructions, action arguments (including generated report content), policies and receipts are visible to room participants. Do not submit secrets. Model prose is generated text, not independently verified evidence; tool receipts document the actual execution.

Runs currently use a bounded synchronous HTTP loop. The dashboard can poll progress while it runs, but other write commands on that node are serialized. There is no background durable queue or cancel button. If the connection is interrupted, inspect the existing task before retrying; an in-flight server call may still finish. Resuming reconstructs tool history from signed events and integrity-checked output artifacts. Unknown tools, malformed arguments, failed upstream calls and over-limit responses do not produce synthetic successes.

The supported tools cover reading text and PDFs, hashing files, CSV import, read-only SQL and report generation. This is not a general shell/browser coding agent. Choose an upstream model with Chat Completions function/tool calling support. The integration follows the [official function-calling protocol](https://developers.openai.com/api/docs/guides/function-calling).

### OpenRouter free and PDFs

Set your server-only configuration's `base_url` to `https://openrouter.ai/api/v1` and `model` to `openrouter/free` (or a tool-capable free model you select). Keep your own API key in `agent-provider.local.json`; it is never sent to the browser. No paid model or OCR fallback is enabled. Free upstream capacity and rate limits still apply.

Attach a PDF directly in the prompt composer. The `pdf.read` tool extracts its text locally with pypdf in a resource/time-limited child process. Every read uses the same artifact authorization, policy checks and signed receipts as other tools. It returns page numbers, text and a continuation cursor, so the agent can read the document beyond the first excerpt. A chunk is 12,000 characters by default, adjustable up to 16,000 per action. The agent must state incomplete coverage when the job or context budget prevents reading everything.

PDF limits: this reads the text layer, not scanned images, diagrams or handwritten pages. Pages with no extractable text are explicitly identified as needing OCR. Encrypted/malformed files fail clearly; table layout may be imperfect. There is no assertion of complete visual understanding. For scans, upload an OCR/text-searchable version. This choice avoids silently using a paid parser: OpenRouter documents distinct free and paid parsing engines in its [PDF guide](https://openrouter.ai/docs/guides/overview/multimodal/pdfs).

Start a **new task** after updating the backend: existing jobs retain their immutable signed tool permissions. Models that return multiple tool calls are handled sequentially, stop at approval boundaries, and cannot exceed the signed action budget. Unproposed remaining calls are not executed after a pause; the next model turn works from the actual signed history.

### Certa interface

The wordmark has no logo icon. All dropdown fields share the supplied monochrome appearance with accessible keyboard navigation. The dock expands on hover/click and collapses after idle pointer/focus leaves; Escape collapses it. Network nodes orbit, respond to the pointer, support keyboard selection and have pause/zoom/reset controls. Only real room members and locally observed connections are drawn. The landing cube follows the cursor; text uses the supplied Hyper Text and Word Rotate treatments. Cursor decoration does not intercept clicks and is hidden for text fields, touch devices and reduced-motion users. Reduced-motion preference changes apply without reloading.

## Install and launch

Use Python 3.10+ and a current Node.js LTS version supported by the frontend dependencies.

```bash
python -m venv .venv
# Activate .venv using your shell's activation command.
python -m pip install -r requirements.txt
cd frontend
npm ci
npm run demo -- --configure .demo-state/operator-profile.json
npm run demo -- --config .demo-state/operator-profile.json
```

**Profile paths are resolved from the repository root**, because the npm wrapper launches Python there. Keep the profile and state directory under `.demo-state/` (gitignored), or outside the repository. Do not commit credentials or personal uploads.

Configuration prompts explain each required value; they deliberately supply no preset host, balance, stake, node name, limits, or timing. Use a reachable local bind address, select protocol version supported by your nodes, and give at least one validator a positive stake covered by its genesis balance. Observers use zero stake. `epoch_ms` controls consensus cadence; `finality_depth` is the number of successor blocks required. The membership refresh interval must be shorter than the membership TTL. Refresh polling must be at least 1000 ms. Resource limits should fit your input and expected outputs. You can edit your private JSON profile between runs.

The launcher prints:

- The actual frontend URL.
- The private `operator-access.json` path, containing each generated node's API URL and access key.

Each launch creates a fresh run directory with real persistent keys, ledger, projections, and artifacts. It does **not** reuse a previous network automatically. Old run directories remain on disk. To resume an existing node, use its saved node configuration with `python -m api --config ...`, restore the corresponding signalling configuration/service, and rejoin its manifest; this is not a one-click launcher resume feature.

## Present the complete flow

1. Open the printed URL. The landing page is explanatory artwork, not simulated network telemetry.
2. Select **Sign in**, choose a running node, and enter that node's generated access key from the private access file. There are no shared/default credentials. The launcher has already created the room; **Manage room** also supports interactive creation/joining.
3. Open **Network**. Verify actual discovered/connected peers. New runs have no jobs or security violations.
4. To demonstrate the manual path, select **Create job → Advanced setup**, enter your title/instructions, choose the configured manual provider, and upload your own file(s). No sample input is bundled.
5. Add an `artifact.hash` permission requiring approval. Select the file that rule may read. Enter your action/runtime/output limits, then create the job.
6. **Accept on this node**. Choose the hash tool and the uploaded file in the action composer. **Propose action** records the signed request and pauses for approval.
7. Review the actual tool arguments/scopes, then approve. The backend reads your file and computes its SHA-256. Download the generated JSON output; compare it with your system's hash utility if desired.
8. To demonstrate denial, include a `report.write` deny rule when creating the job, then propose that tool after the hash finishes. Inspect the real denied decision and violation in **Security**. No report is written for that denied request.
9. Enter a completion summary and complete the job. Watch event states progress from submitted to included to finalized. Real empty successor blocks advance finality when the room becomes quiet; no synthetic events are inserted.
10. Sign in to a different node (another browser context or sign out first) to inspect the same replicated job history. Private file bytes remain on their producing/uploading node.

Other real tools include CSV import, read-only SQL queries over the job workspace, and scoped report writing. The composer obtains tool schemas and declared write scopes from the node. You must grant the corresponding reads/writes in your policy. Raw JSON policies are validated against the shared contract.

## Security and scope

- Sign-in authorizes control of an entire node, not a multi-user SaaS account. Bearer sessions expire and logout revokes the session. Access keys are generated into private files; the frontend never receives signing private keys.
- The launcher is for a trusted local demonstration. Do not expose its development servers publicly. Remote deployment requires TLS, a production server/reverse proxy, access controls and operational hardening.
- Instructions, action arguments, policies, receipts, and artifact metadata are replicated ledger data. Do not put secrets in these fields. File bytes remain local; the ledger does not prove that a remote machine executed honestly.
- Cross-node ownership/worker decisions are verified. Private input transfer between nodes is not implemented: accept file-based jobs on their input-hosting node. Owner approval on another node is recorded, then the assigned worker uses **Execute approved action**.
- This is an educational PoS/pseudo-VRF network, not production blockchain security or a distributed LLM inference engine.
- Height zero is **genesis**, created during room setup before any tasks. It remains visible in Ledger with an explanation but is excluded from Recent blocks. Real empty successor blocks can appear after activity to advance finality.
- The Network graph shows the active room's real peers and only the connections observed by the current node, not an invented complete mesh. Select a node for details. Changing rooms remains available in Manage room.
- Protocol identifiers, schema constraints, UI copy, animation timings, and isolated test fixtures are code constants. Operational records, credentials, endpoints, results, peers, balances and demo inputs are not fabricated in the application.

## Verify without browser mocks

```bash
python -m pytest -q tests
cd frontend
npm run check
npx playwright install chromium
```

In a separate terminal, from the repository root:

```bash
python -m tests.live_server --ready-file /absolute/path/to/a-new-private-access.json
```

Then run Playwright from `frontend` with `AGENTGUARD_LIVE_ACCESS` set to that absolute path. If using installed Chrome, also set `AGENTGUARD_BROWSER_CHANNEL=chrome`.

```bash
npm run test:e2e
```

The verification harness has explicitly test-only resource settings and generates new identities and input bytes. Browser tests do not intercept API responses: they upload data, approve actions, check downloaded hashes, trigger denial, and wait for finality on every node. Test configuration is never imported by the application launcher. Screenshots are produced under ignored `frontend/test-results/`. Stop both launchers with Ctrl+C when finished.
