import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from agentguard.database import connect


class ArtifactError(ValueError): pass


class ArtifactStore:
    def __init__(self, root: Path, max_bytes: int):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.database = self.root / "artifacts.sqlite3"
        with connect(self.database) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS artifacts(
                artifact_id TEXT PRIMARY KEY, room_id TEXT NOT NULL, job_id TEXT,
                name TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL, storage_path TEXT NOT NULL)""")

    def _directory(self, room_id: str, job_id: str | None) -> Path:
        directory=(self.root / room_id / (job_id or "unassigned")).resolve()
        if self.root not in directory.parents:
            raise ArtifactError("artifact scope escapes data root")
        return directory

    def store(self, room_id: str, name: str, media_type: str, stream, job_id: str | None = None) -> dict:
        artifact_id = str(uuid.uuid4())
        if not isinstance(name,str) or not name or len(Path(name).name)>255: raise ArtifactError("artifact name is invalid")
        if not isinstance(media_type,str) or not 0<len(media_type)<=127: raise ArtifactError("artifact media type is invalid")
        directory = self._directory(room_id,job_id)
        directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(); size = 0
        fd, temporary = tempfile.mkstemp(dir=directory, prefix="upload-")
        try:
            with os.fdopen(fd, "wb") as output:
                while True:
                    chunk = stream.read(65536)
                    if not chunk: break
                    size += len(chunk)
                    if size > self.max_bytes: raise ArtifactError("artifact exceeds configured limit")
                    digest.update(chunk); output.write(chunk)
            final = directory / artifact_id
            os.replace(temporary, final)
            ref = {"artifact_id": artifact_id, "name": Path(name).name or "artifact",
                   "media_type": media_type or "application/octet-stream", "size_bytes": size,
                   "sha256": digest.hexdigest()}
            with connect(self.database) as db:
                db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)",
                           (artifact_id, room_id, job_id, ref["name"], ref["media_type"], size,
                            ref["sha256"], str(final.relative_to(self.root))))
            return ref
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def store_bytes(self, room_id, job_id, name, media_type, content: bytes):
        import io
        return self.store(room_id, name, media_type, io.BytesIO(content), job_id)

    def _row(self, room_id: str, artifact_id: str):
        with connect(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM artifacts WHERE room_id=? AND artifact_id=?", (room_id, artifact_id)).fetchone()
        if not row: raise ArtifactError("artifact does not exist in this room")
        return row

    def reference(self, room_id, artifact_id):
        row = self._row(room_id, artifact_id)
        return {key: row[key] for key in ("artifact_id", "name", "media_type", "size_bytes", "sha256")}

    def reference_for_job(self,room_id,job_id,artifact_id):
        row=self._row(room_id,artifact_id)
        if row["job_id"]!=job_id: raise ArtifactError("artifact is not assigned to this job")
        return {key: row[key] for key in ("artifact_id","name","media_type","size_bytes","sha256")}

    def bind(self, room_id: str, artifact_ids: list[str], job_id: str) -> list[dict]:
        refs=[]
        with connect(self.database) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            for artifact_id in artifact_ids:
                row=db.execute("SELECT * FROM artifacts WHERE room_id=? AND artifact_id=?", (room_id,artifact_id)).fetchone()
                if row is None: raise ArtifactError("artifact does not exist in this room")
                if row["job_id"] not in (None, job_id): raise ArtifactError("artifact belongs to another job")
                # Blob paths are immutable. Moving files while a database
                # transaction is open cannot be rolled back if a later bind fails.
                db.execute("UPDATE artifacts SET job_id=? WHERE artifact_id=?", (job_id,artifact_id))
                refs.append({key: row[key] for key in ("artifact_id","name","media_type","size_bytes","sha256")})
        return refs

    def read(self, room_id: str, job_id: str, artifact_id: str) -> bytes:
        row=self._row(room_id, artifact_id)
        if row["job_id"] != job_id: raise ArtifactError("artifact is not assigned to this job")
        path=(self.root / row["storage_path"]).resolve()
        if self.root not in path.parents: raise ArtifactError("artifact path escapes data root")
        data=path.read_bytes()
        if len(data)!=row["size_bytes"] or hashlib.sha256(data).hexdigest()!=row["sha256"]:
            raise ArtifactError("artifact integrity check failed")
        return data
