import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

from agentguard.canonical import decode_signature, signing_bytes
from agentguard.identity import verify
from agentguard.schema_validation import SchemaValidator


class RegistryError(ValueError): pass
class RoomExists(RegistryError): pass
class RoomNotFound(RegistryError): pass


class RoomRegistry:
    def __init__(self, database_path: Path, ttl_ms: int, schemas: SchemaValidator,
                 clock_ms: Callable[[], int] | None = None):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_ms = ttl_ms
        self.schemas = schemas
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS rooms(
                    room_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS members(
                    room_id TEXT NOT NULL, node_id TEXT NOT NULL, name TEXT NOT NULL,
                    advertised_host TEXT NOT NULL, advertised_port INTEGER NOT NULL,
                    public_key_fingerprint TEXT NOT NULL, joined_at_ms INTEGER NOT NULL,
                    last_heartbeat_ms INTEGER NOT NULL,
                    PRIMARY KEY(room_id,node_id),
                    FOREIGN KEY(room_id) REFERENCES rooms(room_id) ON DELETE CASCADE
                );
            """)

    def create_room(self, manifest: dict) -> dict:
        self.schemas.validate_named("room-manifest.schema.json", manifest)
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        with self._lock, self._connect() as db:
            row = db.execute("SELECT manifest_json FROM rooms WHERE room_id=?", (manifest["room_id"],)).fetchone()
            if row:
                if row["manifest_json"] == encoded:
                    return json.loads(row["manifest_json"])
                raise RoomExists("room id is already bound to another manifest")
            payload = signing_bytes("agentguard.room-manifest.v1", manifest, "signature")
            try: signature=decode_signature(manifest["signature"])
            except Exception as exc: raise RegistryError("invalid room manifest signature encoding") from exc
            if not verify(manifest["creator_public_key"], signature, payload):
                raise RegistryError("invalid room manifest signature")
            db.execute("INSERT INTO rooms(room_id,manifest_json) VALUES(?,?)", (manifest["room_id"], encoded))
        return manifest

    def get_room(self, room_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT manifest_json FROM rooms WHERE room_id=?", (room_id,)).fetchone()
        if not row: raise RoomNotFound("room does not exist")
        return json.loads(row["manifest_json"])

    def join(self, room_id: str, request: dict) -> dict:
        self.schemas.validate_named("room-join.schema.json", request)
        self.get_room(room_id)
        now = self.clock_ms()
        with self._lock, self._connect() as db:
            old = db.execute("SELECT joined_at_ms,public_key_fingerprint FROM members WHERE room_id=? AND node_id=?",
                             (room_id, request["node_id"])).fetchone()
            if old and old["public_key_fingerprint"] != request["public_key_fingerprint"]:
                raise RegistryError("node id is already bound to another public key")
            joined = old["joined_at_ms"] if old else now
            db.execute("""INSERT INTO members VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(room_id,node_id) DO UPDATE SET name=excluded.name,
                advertised_host=excluded.advertised_host,advertised_port=excluded.advertised_port,
                last_heartbeat_ms=excluded.last_heartbeat_ms""",
                (room_id, request["node_id"], request["name"], request["advertised_host"],
                 request["advertised_port"], request["public_key_fingerprint"], joined, now))
        return {"schema_version": 1, "room_id": room_id, **request,
                "joined_at_ms": joined, "last_heartbeat_ms": now}

    def heartbeat(self, room_id: str, node_id: str) -> None:
        now = self.clock_ms()
        with self._lock, self._connect() as db:
            cursor = db.execute("UPDATE members SET last_heartbeat_ms=? WHERE room_id=? AND node_id=?",
                                (now, room_id, node_id))
            if not cursor.rowcount: raise RoomNotFound("membership does not exist")

    def list_members(self, room_id: str) -> dict:
        self.get_room(room_id)
        now = self.clock_ms(); cutoff = now - self.ttl_ms
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM members WHERE last_heartbeat_ms < ?", (cutoff,))
            rows = db.execute("SELECT * FROM members WHERE room_id=? ORDER BY node_id", (room_id,)).fetchall()
        return {"items": [{"schema_version": 1, **dict(row)} for row in rows], "server_time_ms": now}

    def leave(self, room_id: str, node_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM members WHERE room_id=? AND node_id=?", (room_id, node_id))
