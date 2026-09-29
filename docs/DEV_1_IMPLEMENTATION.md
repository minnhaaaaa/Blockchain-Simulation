# Developer 1 Implementation Notes

Branch: `dev1/protocol-consensus` (based on `main` at `144ae83`, plus `origin/security-fixes` `0327e13`).

## Where things are

| Concern | Module |
|---|---|
| Canonical JSON / domain-separated signing bytes | `canonical.py` |
| Pseudo-VRF, eligibility, stake snapshot, fork score, double-sign evidence | `consensus/pos/core.py` |
| Signed agent-event validation + per-job state machine | `consensus/pos/events.py` |
| Room manifest verification, deterministic genesis | `consensus/pos/manifest.py` |
| NodeService adapter (Developer 2 interface) | `consensus/pos/node_service.py` |
| Node lifecycle, persisted signer, room transition | `consensus/pos/runtime.py` |
| Per-room/per-node storage | `storage/node_storage.py` |
| PoA authority-set derivation | `consensus/poa/authority.py` |
| Malicious peers (attack only, validation inherited) | `consensus/pos/mal_node.py`, `consensus/poa/mal_node.py` |

## Decisions

* **Pseudo-VRF.** Educational, deterministic. Proof = RFC 6979 ECDSA signature over a domain-separated epoch seed, verified against the creator key and exact seed. The lottery *output* is derived from `(creator key, seed)` only, never from signature bytes, so alternative valid ECDSA signatures cannot be ground. Consequence: the output is publicly computable (no secrecy). Not a standards-based VRF.
* **One eligibility rule.** `core.is_eligible`: `output * total < staked * 2**256`, exact integer arithmetic, used by block production, live validation and chain validation.
* **Signature compatibility (SHA-1 -> SHA-256 / canonical bytes): clean network required.** Persisted state carries `format_version: 2`; anything else is rejected at load with a precise `LegacyStorageError` before networking starts. There is no migration and the two domains are never mixed in one room.
* **Genesis trust anchor.** With a manifest, the genesis block is derived deterministically from the signed manifest; a chain whose first block hashes differently is rejected, however validly self-signed. Sockets are admitted only after a `room_hello` carrying the same room id and genesis hash. Manifest-less legacy CLI use still works and prints a warning. PoA takes an optional `genesis_hash` (the frozen manifest schema is PoS-only).
* **PoA authority.** The set for block N is derived from genesis plus administrator-signed updates carried in earlier blocks (effective height `max(activation, inclusion+1)`, unique update ids). A block's `miners_list` must equal the derived set; it is never a source of authority.
* **Rejection.** `submit_event` raises `SubmissionRejected` (with `.code`) and never queues an invalid event. Events dropped later (reorg, invalidated pool entries) emit `ledger_state: rejected`; orphaned-but-valid events return to `submitted`.
* **Signer.** Loaded/created by `load_or_create_signer` at `<data-root>/.identity/<node-id>/` (the room is unknown at boot) and copied into `<data-root>/<room-id>/<node-id>/` on join; a differing key already stored for a room is refused.
* **Assumption:** default `Authority` treats a job's accepted worker as the gateway for that job. Inject `Authority(is_gateway=..., is_validator=...)` to change it.

## Known limits

* Chain *synchronisation* validates snapshot consistency (signatures, uniqueness, order, positive amounts, affordability, creator stake) but cannot prove completeness: stake announcements are gossip, not on-chain. Completeness is enforced by exact equality on live blocks only.
* PoW `mal_node.py` is still a stale copy (unchanged apart from the shared canonical transaction encoding).
* Peer summaries' `last_seen_ms` comes from signalling membership when known, otherwise first observation.
* `agentguard/schema_validation.py` gained `anyOf` support: without it every `join` room-session request was rejected.

## Running the tests

```bash
pip install -r requirements.txt
python -m pytest -q tests          # 121 tests incl. Developer 2's, three-node runtime tests
python -m unittest discover -s tests -p "test_*.py"   # Developer 2's suite + adapter subclass
```
