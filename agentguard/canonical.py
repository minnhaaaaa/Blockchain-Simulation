import base64
import hashlib
from typing import Any, Mapping
from canonical import canonical_json as _canonical_json, signing_bytes as _signing_bytes


def canonical_json(value: Any) -> str:
    return _canonical_json(value).decode("utf-8")


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def domain_bytes(domain: str, value: Any) -> bytes:
    return _signing_bytes(domain, value)


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def unsigned_copy(value: Mapping[str, Any], *excluded: str) -> dict:
    omitted = set(excluded)
    return {key: item for key, item in value.items() if key not in omitted}


def signing_bytes(domain: str, value: Mapping[str, Any], *excluded: str) -> bytes:
    return domain_bytes(domain, unsigned_copy(value, *excluded))


def encode_signature(signature: bytes) -> str:
    return base64.b64encode(signature).decode("ascii")


def decode_signature(signature: str) -> bytes:
    return base64.b64decode(signature, validate=True)
