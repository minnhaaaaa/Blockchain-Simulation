import base64
import hashlib
import json
from typing import Any, Mapping


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def domain_bytes(domain: str, value: Any) -> bytes:
    return domain.encode("utf-8") + b"\n" + canonical_bytes(value)


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

