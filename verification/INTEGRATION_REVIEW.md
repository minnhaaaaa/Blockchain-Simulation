# Branch Integration Review

Integration target: `main`, combining Developer 1 (`origin/alina`), Developer 3 (`origin/rishav`), and Developer 2's previously merged backend. The `origin/security-fixes` commits are already ancestors of Developer 1's branch; they were reviewed and corrected there, so the standalone branch is not merged a second time.

## What arrived

- `origin/alina`: deterministic PoS pseudo-VRF, signed event state machine, manifest-anchored genesis, PoA authority transitions, node persistence, real NodeService adapter, networking, and regression tests.
- `origin/rishav`: dated Windows verification notes and a runtime signalling config. It contains no React source or browser tests.

## Integration fixes

- Signed room manifests now carry an explicit reserved `stake` for every genesis allocation. The genesis hash commits the complete validator registry; live validation and chain synchronization both require the exact set and amounts. Gossip cannot alter this room registry. Existing room manifests without the new field need a fresh room and data directory; persisted format version 2 alone does not migrate them.
- Room WebSocket admission now requires a signed response to a fresh per-connection challenge. Peer-info keys must match the authenticated socket key.
- Finalized PoS blocks cannot be replaced by a longer fork.
- Double-sign evidence is persisted alongside each node's chain and revalidated on restart and peer synchronization, so a penalty is not silently lost.
- AgentGuard job details and commands are scoped to the active room. Rejected events are removed from the read model, and the current room's projection is rebuilt from node-accepted events on join.
- Added the explicit `python -m api --config ...` node/API launcher, continuous signalling membership refresh, and corrected connected-peer reporting.
- Removed a committed, machine-specific signalling configuration and corrected README clone/run instructions and production claims.

## Verification and remaining release gate

Run the project suite with a Python 3.12 virtual environment and declared requirements:

```bash
python -m pytest -q tests
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q agentguard api consensus signalling smart_contract storage
git diff --check
```

Results on the merged integration checkout: `129 passed` for pytest; the documented unittest discovery command passed its 18 unittest cases; `compileall` and `git diff --check` passed. The pytest run includes real three-node WebSocket convergence, finality, room transition, replay, and restart tests on dynamic ports and temporary storage.

The React dashboard and browser acceptance screenshots are still missing because neither teammate branch contains a `frontend/` project. Do not claim the mandatory web-interface requirement is complete. The Python contract executor remains an educational restricted process, not a production security boundary. Room validator weights are immutable until a signed stake-change transition is implemented. The PoS proof is a deterministic educational pseudo-VRF with publicly computable output. The lottery may have an epoch with no winner; production-grade liveness is not established.
