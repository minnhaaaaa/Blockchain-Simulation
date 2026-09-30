"""Node-local operator authentication; no built-in accounts or credentials."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from pathlib import Path


class OperatorAuth:
    def __init__(self, key_path: Path, session_ttl_seconds: int, clock=time.time):
        if isinstance(session_ttl_seconds, bool) or session_ttl_seconds <= 0:
            raise ValueError("session_ttl_seconds must be positive")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(secrets.token_urlsafe(32))
        key = key_path.read_text(encoding="utf-8").strip()
        if len(key) < 32:
            raise ValueError("operator access key must contain at least 32 characters")
        self._key_hash = hashlib.sha256(key.encode()).digest()
        self._sessions = {}
        self._lock = threading.Lock()
        self.ttl, self.clock = session_ttl_seconds, clock

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode()).digest()

    def login(self, key):
        if not isinstance(key, str) or not hmac.compare_digest(self._digest(key), self._key_hash):
            return None
        token = secrets.token_urlsafe(32)
        expires = self.clock() + self.ttl
        with self._lock:
            self._sessions = {k: v for k, v in self._sessions.items() if v > self.clock()}
            self._sessions[self._digest(token)] = expires
        return {"token": token, "expires_at_ms": int(expires * 1000)}

    def valid(self, token):
        with self._lock:
            return self._sessions.get(self._digest(token), 0) > self.clock()

    def logout(self, token):
        with self._lock:
            self._sessions.pop(self._digest(token), None)
