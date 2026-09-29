"""
Canonical encoding and domain-separated signing bytes (docs/SCHEMAS.md section 3).

Lives at the top level so both the shared structures and every consensus
module use exactly one implementation.
"""
import json
import math
from typing import Any

DOMAIN_TX = "agentguard.transaction.v1"


class CanonicalError(ValueError):
    """Raised when a value has no canonical encoding."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def _reject_non_finite(value: Any):
    if isinstance(value, float) and not math.isfinite(value):
        raise CanonicalError("NON_FINITE_NUMBER", "NaN and infinity cannot be canonicalised")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalError("NON_STRING_KEY", "object keys must be strings")
            _reject_non_finite(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_non_finite(v)


def canonical_json(obj: Any) -> bytes:
    """UTF-8 JSON, sorted keys, compact separators, non-finite numbers rejected."""
    _reject_non_finite(obj)
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def signing_bytes(domain: str, obj: Any) -> bytes:
    """`UTF8(domain + "\\n") || canonical_json(obj)`."""
    return (domain + "\n").encode("utf-8") + canonical_json(obj)
