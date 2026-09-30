import csv
import hashlib
import io
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentguard.artifacts import ArtifactStore
from agentguard.database import connect


class ToolError(ValueError): pass


@dataclass(frozen=True)
class ToolContext:
    room_id: str
    job_id: str
    workspace: Path
    artifacts: ArtifactStore


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    label: str
    description: str
    version: str
    argument_schema: dict
    output_kinds: tuple[str, ...]
    write_scopes: Callable[[dict], list[str]]
    execute: Callable[[ToolContext, dict, list[str]], dict]

    def public(self):
        return {"tool_id": self.tool_id, "label": self.label, "description": self.description,
                "version": self.version, "argument_schema": self.argument_schema,
                "output_kinds": list(self.output_kinds), "write_scopes": self.write_scopes({})}


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition]): self._items={item.tool_id:item for item in definitions}
    def get(self, tool_id):
        if tool_id not in self._items: raise ToolError("tool is not registered")
        return self._items[tool_id]
    def public(self): return [self._items[key].public() for key in sorted(self._items)]


def _artifact_id(args): return args["artifact_id"]
def _ensure_input(args, inputs):
    artifact_id=_artifact_id(args)
    if artifact_id not in inputs: raise ToolError("artifact_id is not declared as an action input")
    return artifact_id

def _read_text(ctx, args, inputs):
    data=ctx.artifacts.read(ctx.room_id, ctx.job_id, _ensure_input(args, inputs))
    if data.startswith(b"%PDF-"):
        raise ToolError("This is a PDF, not plain text. Use pdf.read with this artifact_id to read its pages.")
    return {"value": data.decode(args.get("encoding", "utf-8")), "artifacts": []}

def _read_pdf(ctx, args, inputs):
    data = ctx.artifacts.read(ctx.room_id, ctx.job_id, _ensure_input(args, inputs))
    try:
        result = subprocess.run([sys.executable, "-m", "agentguard.pdf_reader", str(args.get("page", 1)),
            str(args.get("offset", 0)), str(args.get("max_chars", 12000))], input=data,
            capture_output=True, timeout=20, cwd=Path(__file__).resolve().parents[1])
        if result.returncode:
            raise ToolError("PDF extraction exceeded safe processing limits or failed. Split the document and retry.")
        output = json.loads(result.stdout)
        if "error" in output: raise ToolError(output["error"])
        return {"value": output["value"], "artifacts": []}
    except subprocess.TimeoutExpired:
        raise ToolError("PDF extraction timed out. Split the document into smaller files.") from None

def _hash(ctx, args, inputs):
    data=ctx.artifacts.read(ctx.room_id, ctx.job_id, _ensure_input(args, inputs))
    return {"value": {"sha256": hashlib.sha256(data).hexdigest()}, "artifacts": []}

def _safe_identifier(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value) is None:
        raise ToolError("table name is invalid")
    return value

def _database(ctx): ctx.workspace.mkdir(parents=True, exist_ok=True); return ctx.workspace / "job.sqlite3"

def _import_csv(ctx, args, inputs, max_rows):
    artifact=_ensure_input(args, inputs); table=_safe_identifier(args["table_name"])
    rows=list(csv.reader(io.StringIO(ctx.artifacts.read(ctx.room_id,ctx.job_id,artifact).decode("utf-8"))))
    if not rows or not rows[0]: raise ToolError("CSV has no header")
    if len(rows)-1>max_rows: raise ToolError("CSV exceeds configured row limit")
    columns=[_safe_identifier(name) for name in rows[0]]
    if len(set(columns)) != len(columns): raise ToolError("CSV headers must be unique")
    placeholders=",".join("?" for _ in columns); quoted=",".join(f'"{c}" TEXT' for c in columns)
    with connect(_database(ctx)) as db:
        db.execute(f'DROP TABLE IF EXISTS "{table}"'); db.execute(f'CREATE TABLE "{table}" ({quoted})')
        for row in rows[1:]:
            if len(row)!=len(columns): raise ToolError("CSV row width does not match header")
            db.execute(f'INSERT INTO "{table}" VALUES ({placeholders})', row)
    return {"value": {"table": table, "row_count": max(0,len(rows)-1)}, "artifacts": []}

def _query(ctx, args, _inputs, max_rows):
    query=args["query"].strip()
    if not query: raise ToolError("query is empty")
    if args["max_rows"]>max_rows: raise ToolError("requested rows exceed configured tool limit")
    with connect(f"file:{_database(ctx)}?mode=ro", uri=True) as db:
        denied={sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE,sqlite3.SQLITE_CREATE_TABLE,
                sqlite3.SQLITE_DROP_TABLE,sqlite3.SQLITE_ALTER_TABLE,sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH,
                sqlite3.SQLITE_PRAGMA,sqlite3.SQLITE_TRANSACTION}
        db.set_authorizer(lambda action,*_: sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK)
        cursor=db.execute(query); columns=[item[0] for item in cursor.description or []]; rows=cursor.fetchmany(args["max_rows"]+1)
        if len(rows)>args["max_rows"]: raise ToolError("query result exceeds configured row limit")
    return {"value": {"columns": columns, "rows": rows}, "artifacts": []}

def _report(ctx,args,_inputs):
    media={"text":"text/plain","json":"application/json"}[args["format"]]
    content=args["content"] if isinstance(args["content"],str) else json.dumps(args["content"],sort_keys=True)
    ref=ctx.artifacts.store_bytes(ctx.room_id,ctx.job_id,args["name"],media,content.encode())
    return {"value": {"artifact_id": ref["artifact_id"]}, "artifacts": [ref]}

def default_registry(max_query_rows:int, max_csv_rows:int) -> ToolRegistry:
    if max_query_rows<=0 or max_csv_rows<=0: raise ValueError("tool row bounds must be positive")
    obj=lambda props,required: {"type":"object","additionalProperties":False,"required":required,"properties":props}
    aid={"type":"string","format":"uuid"}
    return ToolRegistry([
        ToolDefinition("pdf.read", "Read PDF", "Read text from a permitted PDF locally, without OCR charges. Starts at page 1. Follow next_cursor (page and offset) until null for the whole document; pages without text need OCR. Do not ask users to paste excerpts when a PDF is available.", "1",
            obj({"artifact_id":aid, "page":{"type":"integer","minimum":1}, "offset":{"type":"integer","minimum":0}, "max_chars":{"type":"integer","minimum":1000,"maximum":16000}}, ["artifact_id"]), ("json",), lambda _:[], _read_pdf),
        ToolDefinition("artifact.read_text","Read text","Read one permitted text artifact.","1",obj({"artifact_id":aid,"encoding":{"enum":["utf-8"]}},["artifact_id"]),("text",),lambda _:[],_read_text),
        ToolDefinition("artifact.hash","Hash artifact","Hash one permitted artifact.","1",obj({"artifact_id":aid},["artifact_id"]),("json",),lambda _:[],_hash),
        ToolDefinition("csv.import_sqlite","Import CSV","Import a permitted CSV into the job database.","1",obj({"artifact_id":aid,"table_name":{"type":"string","pattern":"^[A-Za-z_][A-Za-z0-9_]{0,62}$"}},["artifact_id","table_name"]),("table",),lambda _:["job.database"],lambda c,a,i:_import_csv(c,a,i,max_csv_rows)),
        ToolDefinition("sql.query_readonly","Query database","Execute one read-only query.","1",obj({"query":{"type":"string","minLength":1},"max_rows":{"type":"integer","minimum":1}},["query","max_rows"]),("table",),lambda _:[],lambda c,a,i:_query(c,a,i,max_query_rows)),
        ToolDefinition("report.write","Write report","Create a job-scoped text or JSON report.","1",obj({"name":{"type":"string","minLength":1,"maxLength":255},"format":{"enum":["text","json"]},"content":{}},["name","format","content"]),("artifact",),lambda _:["job.outputs"],_report),
    ])
