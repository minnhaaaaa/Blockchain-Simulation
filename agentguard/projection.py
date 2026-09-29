import json
import sqlite3
import threading
from pathlib import Path


class ProjectionError(ValueError): pass


class ProjectionStore:
    def __init__(self, database: Path):
        self.database=Path(database); self.database.parent.mkdir(parents=True,exist_ok=True); self._lock=threading.RLock()
        with self._connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY,room_id TEXT NOT NULL,job_id TEXT NOT NULL,sequence INTEGER NOT NULL,
              event_type TEXT NOT NULL,event_json TEXT NOT NULL,ledger_state TEXT NOT NULL,
              UNIQUE(job_id,sequence));""")
    def _connect(self):
        db=sqlite3.connect(self.database); db.row_factory=sqlite3.Row; return db
    def contains(self,event_id):
        with self._connect() as db: return db.execute("SELECT 1 FROM events WHERE event_id=?",(event_id,)).fetchone() is not None
    def apply(self,event:dict,ledger_state:str):
        encoded=json.dumps(event,sort_keys=True,separators=(",",":"))
        with self._lock,self._connect() as db:
            existing=db.execute("SELECT event_json FROM events WHERE event_id=?",(event["event_id"],)).fetchone()
            if existing:
                if existing["event_json"]!=encoded: raise ProjectionError("event id reused with different content")
                db.execute("UPDATE events SET ledger_state=? WHERE event_id=?",(ledger_state,event["event_id"])); return
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",(event["event_id"],event["room_id"],event["job_id"],event["sequence"],event["event_type"],encoded,ledger_state))
    def _records(self,job_id):
        with self._connect() as db: rows=db.execute("SELECT event_json,ledger_state FROM events WHERE job_id=? ORDER BY sequence",(job_id,)).fetchall()
        return [(json.loads(row["event_json"]),row["ledger_state"]) for row in rows]
    def events(self,job_id): return [event for event,_ in self._records(job_id)]
    def job_ids(self,room_id):
        with self._connect() as db: return [r[0] for r in db.execute("SELECT DISTINCT job_id FROM events WHERE room_id=? ORDER BY job_id",(room_id,))]
    def projection(self,job_id):
        records=self._records(job_id); events=[event for event,_ in records]
        if not events or events[0]["event_type"]!="job.created": raise ProjectionError("job not found")
        source=events[0]["payload"]; status="submitted"; worker=None; actions=completed=pending=0
        for event in events[1:]:
            kind=event["event_type"]
            if kind=="job.accepted": status="accepted"; worker=event["payload"]["worker_public_key"]
            elif kind=="action.proposed": status="running"; actions+=1
            elif kind=="action.approval_required": status="waiting_approval"; pending+=1
            elif kind in ("action.approved","action.rejected"):
                if pending: pending-=1
                status="running"
            elif kind=="action.completed": completed+=1
            elif kind=="job.completed": status="completed"
            elif kind=="job.failed": status="failed"
        latest=events[-1]; latest_state=records[-1][1]
        return {"job_id":source["job_id"],"room_id":source["room_id"],"title":source["title"],
          "owner_fingerprint":__import__('hashlib').sha256(source["owner_public_key"].encode()).hexdigest(),
          "worker_fingerprint":__import__('hashlib').sha256(worker.encode()).hexdigest() if worker else None,
          "provider_id":source["provider_id"],"status":status,"latest_sequence":latest["sequence"],
          "action_count":actions,"completed_action_count":completed,"pending_approval_count":pending,
          "created_at_ms":source["created_at_ms"],"updated_at_ms":latest["created_at_ms"],
          "finality":latest_state if latest_state!="submitted" else "pending"}
    def list_jobs(self,room_id,status=None):
        values=[self.projection(job_id) for job_id in self.job_ids(room_id)]
        return [v for v in values if status is None or v["status"]==status]
    def violations(self,room_id):
        output=[]
        for job_id in self.job_ids(room_id):
            for event,ledger_state in self._records(job_id):
                if event["event_type"]=="security.violation":
                    p=event["payload"]
                    output.append({"violation_id":p["violation_id"],"job_id":job_id,"action_id":p.get("action_id"),
                      "category":p["category"],"code":p["reason_code"],"message":p["message"],
                      "evidence_hash":p["evidence_hash"],"actor_fingerprint":__import__('hashlib').sha256(event["actor_public_key"].encode()).hexdigest(),
                      "detected_at_ms":p["detected_at_ms"],"finality":"pending" if ledger_state=="submitted" else ledger_state})
        return sorted(output,key=lambda v:v["detected_at_ms"],reverse=True)
