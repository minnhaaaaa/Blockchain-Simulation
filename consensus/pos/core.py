"""
Pure consensus rules shared by block production, live validation, chain
validation and the NodeService adapter.

Nothing in here touches the network, the disk or global state, so the three
places that decide "is this block acceptable" cannot drift apart.

Pseudo-VRF note
---------------
This is an educational deterministic pseudo-VRF, not a standards-based VRF.
The proof is an RFC 6979 deterministic ECDSA signature over a
domain-separated epoch seed, and it is verified against the creator's key and
the exact seed. The lottery *output* is derived from (creator key, seed) only,
never from the signature bytes, so a validator cannot grind alternative valid
ECDSA signatures for a favourable output. The price is that the output is
publicly computable rather than secret until the proof is revealed.
"""
import base64
import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from canonical import CanonicalError, canonical_json, signing_bytes
from shared_blockchain_structures import SIGNATURE_HASH, verify_signature

MAX_OUTPUT = 2 ** 256

DOMAIN_BLOCK = "agentguard.pos-block.v1"
DOMAIN_STAKE = "agentguard.pos-stake.v1"
DOMAIN_VRF_SEED = "agentguard.pos-vrf-seed.v1"
DOMAIN_VRF_OUTPUT = "agentguard.pos-vrf-output.v1"

# Bumped whenever signing bytes change. Persisted state carrying another value
# is rejected instead of being silently mixed into the same room.
STORAGE_FORMAT_VERSION = 2


class ConsensusParams:
    """
    Room consensus parameters (room-manifest `consensus.parameters`). The
    legacy() values apply only to the manifest-less interactive CLI.
    """

    __slots__ = ("epoch_ms", "max_clock_skew_ms", "finality_depth", "max_connections", "block_reward", "minimum_stake")

    def __init__(self, epoch_ms, max_clock_skew_ms, finality_depth, max_connections, block_reward, minimum_stake):
        self.epoch_ms = epoch_ms
        self.max_clock_skew_ms = max_clock_skew_ms
        self.finality_depth = finality_depth
        self.max_connections = max_connections
        self.block_reward = block_reward
        self.minimum_stake = minimum_stake

    @classmethod
    def from_manifest(cls, manifest):
        return cls(**manifest["consensus"]["parameters"])

    @classmethod
    def legacy(cls):
        return cls(60000, 10000, 50, 8, 6, 1)

    @property
    def epoch_seconds(self):
        return self.epoch_ms / 1000

    @property
    def min_block_spacing_seconds(self):
        return self.epoch_seconds * 5 / 6


class ConsensusError(Exception):
    """A consensus rule was violated. `code` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


# --------------------------------------------------------------------------
# Canonical encoding
# --------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def b64(data: Optional[bytes]) -> Optional[str]:
    return None if data is None else base64.b64encode(data).decode()


# --------------------------------------------------------------------------
# Pseudo-VRF
# --------------------------------------------------------------------------

def vrf_seed_bytes(epoch_seed: str) -> bytes:
    return signing_bytes(DOMAIN_VRF_SEED, {"epoch_seed": str(epoch_seed)})


def vrf_prove(private_key, epoch_seed: str) -> bytes:
    """Deterministic proof for the exact (key, epoch seed) input."""
    return private_key.sign_deterministic(vrf_seed_bytes(epoch_seed), hashfunc=SIGNATURE_HASH)


def vrf_verify_proof(creator_public_key_pem: str, proof: bytes, epoch_seed: str) -> bool:
    """The proof must be a valid signature by the creator over the exact seed."""
    return verify_signature(creator_public_key_pem, proof, vrf_seed_bytes(epoch_seed))


def vrf_output_int(creator_public_key_pem: str, epoch_seed: str) -> int:
    """
    Lottery output. Depends only on the creator key and the seed, so it is
    identical for every valid proof and cannot be ground.
    """
    digest = hashlib.sha256(
        signing_bytes(
            DOMAIN_VRF_OUTPUT, {"creator": creator_public_key_pem, "epoch_seed": str(epoch_seed)}
        )
    ).hexdigest()
    return int(digest, 16)


def is_eligible(output_int: int, staked_amt: int, total_stake: int) -> bool:
    """
    The one eligibility boundary. Eligible only when the output is strictly
    below staked/total * 2**256; evaluated exactly, without floating point.
    """
    if total_stake <= 0 or staked_amt <= 0 or staked_amt > total_stake:
        return False
    return output_int * total_stake < staked_amt * MAX_OUTPUT


# --------------------------------------------------------------------------
# Stake snapshot
# --------------------------------------------------------------------------

def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def stake_signing_string(stake_dict: Dict[str, Any]) -> str:
    return signing_bytes(DOMAIN_STAKE, stake_dict).decode("utf-8")


def sort_snapshot(stakes: Iterable[Any]) -> List[Any]:
    """Snapshots are ordered by staker identity, nothing else."""
    return sorted(stakes, key=lambda s: s.staker)


def validate_stake_snapshot(
    stakes: List[Any],
    creator: str,
    declared_stake: int,
    minimum_stake: int = 1,
    require_sorted: bool = True,
) -> int:
    """
    Validate an ordered stake snapshot and return the total stake.

    Each stake object needs `.staker`, `.amt`, `.sign` and `__str__` giving its
    signing string. Raises ConsensusError with a stable code.
    """
    seen = set()
    total = 0
    creator_stake = None
    previous = None
    for stake in stakes:
        if not _is_int(stake.amt) or stake.amt < minimum_stake or stake.amt <= 0:
            raise ConsensusError("BAD_STAKE_AMOUNT", "stake must be a positive integer")
        if stake.staker in seen:
            raise ConsensusError("DUPLICATE_STAKER", "stake identities must be unique")
        seen.add(stake.staker)
        if not verify_signature(stake.staker, stake.sign, str(stake)):
            raise ConsensusError("INVALID_STAKE_SIGNATURE", "stake signature does not verify")
        if require_sorted and previous is not None and stake.staker < previous:
            raise ConsensusError("SNAPSHOT_NOT_ORDERED", "stake snapshot is not deterministically ordered")
        previous = stake.staker
        if stake.staker == creator:
            creator_stake = stake.amt
        total += stake.amt
    if total <= 0:
        raise ConsensusError("ZERO_TOTAL_STAKE", "snapshot has no stake")
    if creator_stake is None:
        raise ConsensusError("CREATOR_NOT_STAKED", "creator is not in the snapshot")
    if creator_stake != declared_stake:
        raise ConsensusError("CREATOR_STAKE_MISMATCH", "declared stake differs from the authenticated stake")
    return total


def snapshot_matches(stakes: Iterable[Any], authenticated: Dict[str, int]) -> bool:
    """Exact equality between a block snapshot and the locally authenticated one."""
    block_view = {}
    for stake in stakes:
        if stake.staker in block_view:
            return False
        block_view[stake.staker] = stake.amt
    return block_view == dict(authenticated)


# --------------------------------------------------------------------------
# Fork choice
# --------------------------------------------------------------------------

def chain_score(blocks: List[Any]) -> Tuple[int, int, str]:
    """
    Deterministic fork score from authenticated fields only:
    (cumulative snapshot stake, length, negated-tip-hash ordering key).
    Higher is better. The final element is a tie breaker every node computes
    identically, so arrival order can never change the outcome.
    """
    weight = 0
    for block in blocks:
        for stake in block.stakers:
            weight += stake.amt
    tip = blocks[-1].hash if blocks else ""
    # Lower tip hash wins ties: invert each hex digit so "higher is better".
    inverted = "".join("%x" % (15 - int(c, 16)) for c in tip)
    return (weight, len(blocks), inverted)


def better_chain(candidate: List[Any], current: List[Any]) -> bool:
    return chain_score(candidate) > chain_score(current)


# --------------------------------------------------------------------------
# Double signing
# --------------------------------------------------------------------------

def double_sign_key(block: Any, height: int) -> Tuple[str, int, str]:
    return (block.creator, height, block.seed)


def validate_double_sign_evidence(block_a: Any, block_b: Any, height_a: int, height_b: int) -> Tuple[str, int, str]:
    """
    Evidence is slashable only when both blocks share creator, height and
    epoch seed, differ in signed hash, and carry valid creator signatures over
    their own bytes. Returns the idempotency key; raises ConsensusError.
    """
    if not block_a.creator or block_a.creator != block_b.creator:
        raise ConsensusError("EVIDENCE_CREATOR_MISMATCH", "different creators is a normal fork")
    if height_a != height_b:
        raise ConsensusError("EVIDENCE_HEIGHT_MISMATCH", "blocks are at different heights")
    if block_a.seed != block_b.seed:
        raise ConsensusError("EVIDENCE_SEED_MISMATCH", "blocks belong to different epochs")
    if block_a.hash == block_b.hash:
        raise ConsensusError("EVIDENCE_IDENTICAL", "identical blocks are not evidence")
    if not verify_signature(block_a.creator, block_a.sign, str(block_a)):
        raise ConsensusError("EVIDENCE_BAD_SIGNATURE", "first block signature is invalid")
    if not verify_signature(block_b.creator, block_b.sign, str(block_b)):
        raise ConsensusError("EVIDENCE_BAD_SIGNATURE", "second block signature is invalid")
    return double_sign_key(block_a, height_a)
