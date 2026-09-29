"""
PoA authority-set evolution.

The set of authorities that may sign block N is a pure function of the chain
before N: the genesis set, changed only by updates signed by the genesis
administrator and carried in earlier blocks. A block's own `miners_list`
field is never a source of authority - it must equal the derived set - so a
signer cannot promote itself (or anyone else) by writing a new list into a
block it signs.

Effective height of an update = max(activation_block, inclusion_height + 1),
so an update that reaches the chain late still applies deterministically.
Update ids are unique across the chain (replay protection).
"""
from typing import Any, Dict, List

from canonical import signing_bytes
from shared_blockchain_structures import verify_signature

DOMAIN = "agentguard.poa-authority.v1"
MAX_UPDATES_PER_BLOCK = 16


class AuthorityError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def _shape_ok(update: Any) -> bool:
    if not isinstance(update, dict):
        return False
    miners = update.get("miners_list")
    activation = update.get("activation_block")
    return (
        isinstance(update.get("id"), str) and bool(update["id"])
        and isinstance(miners, list) and bool(miners)
        and all(isinstance(m, str) and m for m in miners) and len(set(miners)) == len(miners)
        and isinstance(activation, int) and not isinstance(activation, bool) and activation >= 0
        and isinstance(update.get("signature"), str)
    )


def update_signing_bytes(update: Dict[str, Any]) -> bytes:
    return signing_bytes(DOMAIN, {
        "id": update["id"], "miners_list": update["miners_list"], "activation_block": update["activation_block"],
    })


def sign_update(private_key, update_id: str, miners_list: List[str], activation_block: int) -> Dict[str, Any]:
    update = {"id": update_id, "miners_list": list(miners_list), "activation_block": activation_block}
    update["signature"] = private_key.sign(update_signing_bytes(update)).hex()
    return update


def verify_update(admin_public_key: str, update: Any) -> bool:
    if not admin_public_key or not _shape_ok(update):
        return False
    try:
        signature = bytes.fromhex(update["signature"])
    except ValueError:
        return False
    return verify_signature(admin_public_key, signature, update_signing_bytes(update))


def authority_set_for_height(blocks: List[Any], height: int) -> List[str]:
    """
    The authorities allowed to sign the block at index `height`, derived only
    from blocks[0:height]. blocks[0] (genesis) defines the initial set and the
    administrator (its signer).
    """
    if not blocks or height < 1 or height > len(blocks):
        raise AuthorityError("BAD_HEIGHT", "no derived authority set for that height")
    genesis = blocks[0]
    admin = genesis.miner_public_key
    active = list(genesis.miners_list or [])
    if not active:
        raise AuthorityError("NO_GENESIS_AUTHORITIES", "genesis lists no authorities")
    scheduled = []            # (effective_height, inclusion_height, position, miners_list)
    seen_ids = set()
    for included_at in range(1, height):
        for position, update in enumerate(getattr(blocks[included_at], "authority_updates", None) or []):
            if not verify_update(admin, update):
                raise AuthorityError("BAD_UPDATE", f"block {included_at} carries an update not signed by the administrator")
            if update["id"] in seen_ids:
                raise AuthorityError("UPDATE_REPLAYED", f"update {update['id']} appears twice")
            seen_ids.add(update["id"])
            scheduled.append((max(update["activation_block"], included_at + 1), included_at, position, update["miners_list"]))
    for effective, _, _, miners in sorted(scheduled, key=lambda s: s[:3]):
        if effective <= height:
            active = list(miners)
    return active


def validate_block_authority(previous_blocks: List[Any], block: Any) -> None:
    """
    Raise AuthorityError unless `block` (to be appended after previous_blocks)
    is signed by a derived authority, declares exactly the derived set, and
    carries only well-formed, admin-signed, non-replayed updates.
    """
    height = len(previous_blocks)
    expected = authority_set_for_height(previous_blocks, height)
    if list(block.miners_list or []) != expected:
        raise AuthorityError("AUTHORITY_SET_MISMATCH", "block declares an authority set that was not derived from admin updates")
    if block.miner_node_id not in expected:
        raise AuthorityError("NOT_AN_AUTHORITY", "block signer is not in the derived authority set")
    updates = list(getattr(block, "authority_updates", None) or [])
    if len(updates) > MAX_UPDATES_PER_BLOCK:
        raise AuthorityError("TOO_MANY_UPDATES", "too many authority updates in one block")
    admin = previous_blocks[0].miner_public_key
    used = {u["id"] for b in previous_blocks[1:] for u in (getattr(b, "authority_updates", None) or [])}
    for update in updates:
        if not verify_update(admin, update):
            raise AuthorityError("BAD_UPDATE", "authority update is not signed by the administrator")
        if update["id"] in used:
            raise AuthorityError("UPDATE_REPLAYED", "authority update was already applied or included")
        if update["activation_block"] <= height:
            raise AuthorityError("UPDATE_NOT_IN_FUTURE", "an update must activate after the block that carries it")
        used.add(update["id"])
