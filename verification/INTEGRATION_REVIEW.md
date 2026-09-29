# Developer 3 Integration Review

## Exact clean-terminal failure

Command:

```powershell
python --version
```

Output:

```text
python: The term 'python' is not recognized as a name of a cmdlet, function, script file, or executable program.
```

The integrated run continued with a repository-local `.venv` created from the available Python runtime. The documented `python` command remains an environment prerequisite.

## Existing Python test suite on this Windows host

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result:

```text
16 failed, 113 passed in 17.29s
```

Fifteen failures are teardown failures where SQLite files such as `artifacts.sqlite3`, `projection.sqlite3`, or `rooms.sqlite3` remain open when `TemporaryDirectory.cleanup()` runs (`PermissionError: [WinError 32]`). The remaining failure expects a POSIX `0600` mode but Windows reports `0666`. Developer 3 did not change Python storage lifecycles or permission rules.

## Open backend/contract failures

### Uploaded artifact cannot be bound to a new job

Real UI operation: upload `verification/demo-input.csv`, then submit the job.

HTTP result: `POST /api/jobs` returned 500 HTML, which the typed client truthfully reported as `Server returned invalid JSON.`

Backend traceback excerpt (verbatim):

```text
File "agentguard\artifacts.py", line 89, in bind
    if old != target: os.replace(old, target)
FileNotFoundError: [WinError 3] The system cannot find the path specified
```

Developer 3 did not change the Python artifact store.

### Job creation response cannot identify the created job

`POST /api/jobs` returns `Submission` (`submission_id`, `event_id`, `ledger_state`, optional `event_hash`) but no `job_id`. The frontend therefore shows the submitted event and reconciles via the jobs collection; it cannot truthfully navigate directly to the created job as required by the frontend specification.

### Manual-provider proposal is not browser-constructible

The only configured production provider kind is `manual`. `POST /api/jobs/{job_id}/actions` requires an `action.schema.json` payload containing `proposer_public_key`, but `GET /api/status` exposes only `node_public_key_fingerprint`. The real **Run next action** operation returns:

```text
manual provider requires an action submitted through the API
```

No full public key or browser-safe “propose manual action” request exists in the API contract, so live approval, receipt, completion, and malicious-proposal demonstrations cannot be driven entirely from the browser.

## Frontend/harness defects found and fixed during the live run

- Ajv registry now rebases contract URNs before resolving relative schema references.
- Generated harness PEM is canonicalized to the Python signer representation.
- The room form preserves public-key PEM bytes instead of trimming the trailing newline.
- Removing an uploaded artifact also removes its ID from policy read grants.
- Windows Vite launch uses Node directly instead of spawning `npm.cmd`.

## Claims audit

- No React UI claim uses “secure” or “distributed AI.”
- “Verified” in the implementation documentation refers to concrete signature/path validation and is supported by schema/runtime tests.
- “Private” appears only in negative-disclosure statements (private keys and artifact contents are not rendered). The live Settings/Gateway surfaces comply.
- The root README still describes broad legacy features (selectable PoW/PoS/PoA, smart-contract deployment, IPFS integration, malicious node) without tying each claim to this AgentGuard acceptance run. Those claims should not be used in the five-minute AgentGuard demonstration.
