# Developer 2 Implementation Guide

## Delivered modules

- `signalling/`: immutable signed room manifests, room-isolated membership, heartbeat expiry, HTTP service, and client.
- `agentguard/schema_validation.py`: runtime validation driven by the committed JSON Schemas.
- `agentguard/artifacts.py`: bounded, content-hashed, room/job-scoped artifact storage with integrity checks.
- `agentguard/policy.py`: deterministic deny-by-default permission evaluation.
- `agentguard/tools.py`: registered artifact, CSV, SQLite, report, and hashing tools; there is no shell or generated-Python tool.
- `agentguard/providers.py`: injected provider registry and explicit manual provider.
- `agentguard/worker.py`: signed job/action/decision/receipt/result/violation event orchestration.
- `agentguard/projection.py`: rebuildable SQLite job and violation read model.
- `agentguard/node_service.py`: strict integration boundary for Developer 1's PoS node adapter.
- `api/app.py`: Flask application API matching `contracts/openapi.json`.

Production construction requires a real `NodeService`, a persisted signer supplied by the node integration, explicit configuration, and explicit provider registration. Test fakes live only in `tests/fakes.py`.

## Run the signalling service

Create a local JSON configuration outside committed production code with values chosen for the current run:

```json
{
  "bind_host": "<bind-host>",
  "bind_port": 0,
  "database_path": "<writable-database-path>",
  "membership_ttl_ms": 0,
  "max_request_bytes": 0
}
```

Replace every placeholder and zero with a valid runtime value; zero is intentionally rejected. Then run:

```bash
python -m signalling --config <path-to-config.json>
```

The service never creates a room or member automatically. A node/application creates or joins through the signed room APIs.

## Application composition

The application is an app factory because Developer 1's node implementation owns chain identity, signing-key persistence, P2P lifecycle, and finality. Construct these dependencies explicitly:

1. `ApplicationConfig.from_mapping(...)`.
2. `SchemaValidator` pointed at `contracts/schemas`.
3. Node-backed `Signer` and `NodeService` implementations.
4. `ArtifactStore`, `ProjectionStore`, `PolicyEvaluator`, `default_registry(...)`, and explicit `ProviderRegistry`; schema-depth/node and CSV/query row bounds are required runtime inputs.
5. `SignallingClient` and `RoomSessionCoordinator`, with its verified-room callback connected to the node's P2P room transition.
6. `AgentRuntime` and `api.app.create_app(...)`.

The room callback must make the node verify/apply the manifest and reconnect before the application claims the new room is operational. The React client supplies the application origin at runtime; it is never embedded here.

## Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

The current suite covers configuration failure, schema rejection, manifest signatures/immutability, room isolation/expiry, artifact containment/integrity, deny-by-default policy behavior, CSV import, read-only SQL, honest action execution, signed receipts, approval/replay prevention, denial violations, terminal job validation, and browser-safe room creation.

Developer 1 must additionally run these tests against the real node adapter and add multi-node finality/reorg cases. Developer 3 should generate client types from the updated OpenAPI contract and run browser tests against this app factory wired to the real adapter.

## Security boundaries

- The signalling database is discovery state, never consensus authority.
- Browser room creation sends unsigned parameters to the local node; private keys never enter the browser.
- Provider output is only an action proposal. Only the gateway invokes tools.
- Unknown tools, missing policy matches, excess artifacts/writes/arguments, expired jobs/policies, repeated decisions, and invalid transitions fail closed.
- Uploaded names are metadata. Generated IDs and verified paths select storage.
- SQLite query execution uses read-only mode plus an authorizer that rejects mutation and attachment operations.
- Rejected ledger submissions are not projected as accepted job history.
