# AgentGuard Lite Contracts

This directory is the shared implementation boundary for all three workstreams.

- `openapi.json` defines the signalling and application HTTP operations.
- `schemas/` defines signed ledger records, room records, browser request bodies, and shared primitives using JSON Schema draft 2020-12.
- `docs/SCHEMAS.md` defines canonicalization, signatures, invariants, and state transitions.
- `docs/API_CONTRACT.md` defines HTTP behavior, errors, finality, and the in-process node boundary.

## Rules

1. Validate inputs and outputs against these files at process boundaries.
2. Generate or derive TypeScript wire types from these files; do not hand-copy interfaces.
3. Keep Python and TypeScript canonical-JSON fixtures identical.
4. Do not embed example/runtime records in production modules or the frontend bundle.
5. Coordinate a contract commit before implementing a breaking field, type, state, route, hash, or signing change.
6. Use symbolic placeholders in documentation and test-only values under test fixture directories.

## Validation

From the repository root, JSON syntax can be checked without installing project dependencies:

```bash
for file in contracts/openapi.json contracts/schemas/*.json; do
  python3 -m json.tool "$file" >/dev/null
done
```

Implementation CI should additionally run a JSON Schema/OpenAPI validator, generated-client typecheck, backend contract tests, and browser contract tests.
