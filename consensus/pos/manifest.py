"""
Signed room manifest: the trust anchor for a room's genesis.

A node with no local chain accepts only the genesis derived from a verified
manifest. It never trusts "the first valid self-signed genesis received".
"""
import base64
import uuid
from typing import Any, Dict, List

from consensus.pos.blockchain_structures import Block, Transaction
from consensus.pos.events import manifest_signing_bytes, schema_errors, _verify_b64


class ManifestError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def sign_manifest(unsigned: Dict[str, Any], private_key) -> Dict[str, Any]:
    manifest = {k: v for k, v in unsigned.items() if k != "signature"}
    manifest["signature"] = base64.b64encode(private_key.sign(manifest_signing_bytes(manifest))).decode()
    return manifest


def verify_manifest(manifest: Any, expected_room_id: str = None) -> Dict[str, Any]:
    """Schema, signature and identity checks. Returns the manifest or raises ManifestError."""
    if not isinstance(manifest, dict):
        raise ManifestError("VALIDATION_FAILED", "manifest must be an object")
    errors = schema_errors("room-manifest", manifest)
    if errors:
        raise ManifestError("VALIDATION_FAILED", "; ".join(errors[:5]))
    if not _verify_b64(manifest["creator_public_key"], manifest["signature"], manifest_signing_bytes(manifest)):
        raise ManifestError("INVALID_SIGNATURE", "manifest signature does not verify for its creator")
    if expected_room_id is not None and manifest["room_id"] != expected_room_id:
        raise ManifestError("ROOM_ALREADY_EXISTS", "room_id is bound to a different manifest")
    keys = [a["public_key"] for a in manifest["genesis"]["allocations"]]
    if len(set(keys)) != len(keys):
        raise ManifestError("VALIDATION_FAILED", "genesis allocations must have unique public keys")
    return manifest


def build_genesis(manifest: Dict[str, Any]) -> Block:
    """
    Deterministic genesis block: every node derives identical bytes from the
    manifest. The block is not separately signed; its authority is that its
    hash equals the hash derived from the creator-signed manifest.
    """
    genesis_desc = manifest["genesis"]
    transactions: List[Transaction] = []
    for index, allocation in enumerate(genesis_desc["allocations"]):
        tx_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentguard:{manifest['room_id']}:{genesis_desc['block_id']}:{index}"))
        transactions.append(
            Transaction(allocation["amount"], "Genesis", allocation["public_key"], id=tx_id, ts=genesis_desc["created_at_ms"])
        )
    block = Block(None, transactions, ts=genesis_desc["created_at_ms"], id=genesis_desc["block_id"])
    block.creator = manifest["creator_public_key"]
    return block


def genesis_hash(manifest: Dict[str, Any]) -> str:
    return build_genesis(manifest).hash
