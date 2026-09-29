import hashlib
from dataclasses import dataclass
from typing import Protocol

from ecdsa import BadSignatureError, SECP256k1, SigningKey, VerifyingKey


class Signer(Protocol):
    @property
    def public_key_pem(self) -> str: ...
    def sign(self, payload: bytes) -> bytes: ...


@dataclass(frozen=True)
class EcdsaSigner:
    private_key: SigningKey

    @classmethod
    def generate(cls) -> "EcdsaSigner":
        return cls(SigningKey.generate(curve=SECP256k1, hashfunc=hashlib.sha256))

    @classmethod
    def from_pem(cls, pem: str) -> "EcdsaSigner":
        return cls(SigningKey.from_pem(pem, hashfunc=hashlib.sha256))

    @property
    def public_key_pem(self) -> str:
        return self.private_key.verifying_key.to_pem().decode("ascii")

    def sign(self, payload: bytes) -> bytes:
        return self.private_key.sign_deterministic(payload, hashfunc=hashlib.sha256)


def verify(public_key_pem: str, signature: bytes, payload: bytes) -> bool:
    try:
        key = VerifyingKey.from_pem(public_key_pem.encode("ascii"), hashfunc=hashlib.sha256)
        return key.verify(signature, payload, hashfunc=hashlib.sha256)
    except (BadSignatureError, ValueError, TypeError, UnicodeError):
        return False


def fingerprint(public_key_pem: str) -> str:
    return hashlib.sha256(public_key_pem.encode("utf-8")).hexdigest()

