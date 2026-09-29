"""
Per-node persistence namespaced by room and node:

    <data_root>/<room_id>/<node_id>/

Nothing is derived from a default location. Missing configuration is an error,
and state written under an older signing domain is rejected with a precise
message rather than being silently mixed with the current one.
"""
import json
import os
import re
from typing import Any, Optional

STORAGE_FORMAT_VERSION = 2

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class StorageConfigError(Exception):
    pass


class LegacyStorageError(Exception):
    """Persisted state predates the canonical SHA-256 signing domain."""


def _component(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT.match(value) or value in (".", ".."):
        raise StorageConfigError(f"{name} is missing or not a safe path component")
    return value


class NodeStorage:
    def __init__(self, data_root: Optional[str], room_id: Optional[str], node_id: Optional[str]):
        if not data_root:
            raise StorageConfigError("data_root is required; there is no default storage location")
        self.room_id = _component("room_id", room_id)
        self.node_id = _component("node_id", node_id)
        self.dir = os.path.join(os.path.abspath(data_root), self.room_id, self.node_id)
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def _write(self, name: str, value: Any):
        tmp = self._path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"format_version": STORAGE_FORMAT_VERSION, "data": value}, fh, indent=2)
        os.replace(tmp, self._path(name))

    def _read(self, name: str):
        path = self._path(name)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or doc.get("format_version") != STORAGE_FORMAT_VERSION:
            raise LegacyStorageError(
                f"{path} was written under an older signing domain (no format_version {STORAGE_FORMAT_VERSION}). "
                "Signatures changed from SHA-1 / ad-hoc JSON to SHA-256 over canonical bytes and are not "
                "compatible; start a clean network with a fresh data directory."
            )
        return doc["data"]

    def save_key(self, private_key_pem: str):
        self._write("keys.json", {"private_key_pem": private_key_pem})
        os.chmod(self._path("keys.json"), 0o600)

    def load_key(self) -> Optional[str]:
        doc = self._read("keys.json")
        return doc["private_key_pem"] if doc else None

    def save_chain(self, chain_dicts):
        self._write("chain.json", chain_dicts)

    def load_chain(self):
        return self._read("chain.json")

    def save_evidence(self, records):
        self._write("evidence.json", records)

    def load_evidence(self):
        return self._read("evidence.json") or []

    def save_manifest(self, manifest):
        existing = self._read("manifest.json")
        if existing is not None and existing != manifest:
            raise StorageConfigError("a different manifest is already stored for this room")
        self._write("manifest.json", manifest)

    def load_manifest(self):
        return self._read("manifest.json")

    def save_peers(self, peers):
        self._write("peers.json", peers)

    def load_peers(self):
        return self._read("peers.json")
