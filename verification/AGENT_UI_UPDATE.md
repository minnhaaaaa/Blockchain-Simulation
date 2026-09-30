# Agent and monochrome UI update

Implemented on 2026-09-30; not a production-security certification.

- Prompt-first job creation; advanced policy editor and manual tools retained.
- OpenAI-compatible Chat Completions transport with configurable endpoint, model and server-only key. No fallback model or canned response.
- Model tool proposals are validated and signed by the runtime; real tool results are fed back; writes pause for owner approval.
- Empty/malformed/oversized responses and upstream failures surface explicit errors. Completed tasks cannot run again.
- Genesis is identified in Ledger and excluded from Recent blocks.
- Current-room graph uses actual peers and locally observed edges, with accessible detail buttons. No hypothetical mesh edges or seeded membership.
- Monochrome dashboard, adapted supplied spring dock, lazy-loaded Three.js landing cube, scoped GSAP transitions and reduced-motion handling.
- Company Brain's graph-focused interface informed the network layout; no Company Brain code or data was incorporated.

Verification: Python regression suite, frontend type/lint/unit/build checks, desktop/mobile Playwright using real signalling/HTTP/P2P APIs, and an isolated compatible HTTP protocol server testing a real hash tool and three-node finality. Protocol-response fixtures exist only under tests. Hosted model credentials, availability and answer quality remain unverified until the operator configures and runs that provider.

Limits: synchronous node-serialized writes while the model loop runs; no durable background runner/cancel; local private-file availability; educational PoS rather than production security. Model prose is not cryptographic proof of correctness. Editable resource settings are configuration, not simulated runtime data.
