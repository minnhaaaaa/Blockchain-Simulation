# Claims Audit

Audit timestamp: 2026-09-29 21:39:58 +05:30  
Scope: repository Markdown and available application source. There is no UI to audit.

## Claims requiring correction or qualification

| Location | Claim | Finding | Recommended wording/action |
|---|---|---|---|
| `README.md:5` | “Peer-to-Peer network with decentralized communication” | Not demonstrated in this run; the application cannot be installed or started on the verification host. | Label as an intended/legacy capability until a repeatable multi-node run passes. |
| `README.md:12` | “Malicious node to test security” | Source files exist, but no documented repeatable security test or captured result is present. | Say “includes malicious-node test code” and link to executable tests/results. |
| `README.md:139` | Contracts “run inside a sandboxed environment” | A child process, timeout, memory check, and `RestrictedPython` are present, but the build provides no evidence of production-grade isolation. `TECH_STACK.md:341` itself limits this claim. | Use “restricted educational executor with resource limits; not a security boundary.” |
| `README.md:149-152` | Security/robustness tested; protocols are working and network functional | No `tests/` directory or evidence report exists, and the documented commands fail on a clean run. | Remove or attach dated, reproducible test evidence and scope the claim. |
| `README.md:7` and introductory text | Web interface / “web and terminal” implementation | No HTML/JS/TS/TSX/frontend package exists. | Mark the web interface as planned until implemented. |
| `PLAN.md:5-7` | AgentGuard Lite “is” an executable research prototype whose malicious/replayed actions are rejected and shown in a dashboard | This checkout contains a target plan, not the implementation. | Change present tense to target/future tense until acceptance passes. |
| `TECH_STACK.md:108-341` | Signalling behavior, immutable manifests, live dashboard state, key handling, rejections, finality, and security controls | These are architecture specifications, not demonstrated build behavior. | Keep them explicitly under “target design” and avoid presenting them as completed features. |
| `TECH_STACK.md:174` | Private keys remain in configured node storage | Legacy `storage/storage_manager.py:36-41` stores PEM private-key material as plain JSON under a consensus directory, not a configurable per-node AgentGuard storage directory. | Do not imply encrypted/private storage; describe exact at-rest handling and permissions. |

## Search results

- `distributed AI`: no occurrence.
- `secure`: appears mainly in Python class/module names such as `SecureContractExecutor`; a name is not verification.
- `verified`: appears in comments/design prose, not in a completed acceptance record.
- `private`: mostly refers to cryptographic private keys; it must not be interpreted as a privacy guarantee.
- `distributed`, `decentralized`, `trustless`, `sandbox`, `security`, `robust`, `functional`, `live`, `finalized`, and `reject`: multiple documentation occurrences are either general theory or target-design statements and should not be used as release claims without passing evidence.

## Safe presentation language

Use: “local educational prototype,” “planned deny-by-default workflow,” “signed-event design,” and “acceptance pending.” Avoid: “secure,” “verified AI,” “private distributed AI,” “production sandbox,” or “fully functional network” for this build.

