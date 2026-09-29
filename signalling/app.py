import uuid
from pathlib import Path

from flask import Flask, g, has_request_context, jsonify, request
from werkzeug.exceptions import BadRequest

from agentguard.config import SignallingConfig
from agentguard.schema_validation import SchemaValidationError, SchemaValidator
from signalling.registry import RegistryError, RoomExists, RoomNotFound, RoomRegistry


def _error(code: str, message: str, status: int, details: dict | None = None):
    request_id=getattr(g,"request_id",None) if has_request_context() else None
    body = {"code": code, "message": message, "request_id": request_id or str(uuid.uuid4())}
    if details: body["details"] = details
    return jsonify(body), status


def create_app(config: SignallingConfig, registry: RoomRegistry | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.max_request_bytes
    schemas = SchemaValidator(Path(__file__).resolve().parents[1] / "contracts" / "schemas")
    registry = registry or RoomRegistry(config.database_path, config.membership_ttl_ms, schemas)

    @app.before_request
    def assign_request_id(): g.request_id=str(uuid.uuid4())
    @app.after_request
    def expose_request_id(response): response.headers["X-Request-ID"]=g.request_id; return response

    @app.errorhandler(SchemaValidationError)
    def schema_error(exc): return _error("VALIDATION_FAILED", str(exc), 422)
    @app.errorhandler(RoomNotFound)
    def missing(exc): return _error("ROOM_NOT_FOUND", str(exc), 404)
    @app.errorhandler(RoomExists)
    def exists(exc): return _error("ROOM_ALREADY_EXISTS", str(exc), 409)
    @app.errorhandler(RegistryError)
    def registry_error(exc): return _error("VALIDATION_FAILED", str(exc), 422)
    @app.errorhandler(413)
    def too_large(_): return _error("PAYLOAD_TOO_LARGE", "request exceeds configured limit", 413)
    @app.errorhandler(BadRequest)
    def bad_request(_): return _error("VALIDATION_FAILED","request body is not valid JSON",422)

    @app.get("/health")
    def health(): return jsonify({"status": "ok"})
    @app.post("/api/rooms")
    def create_room(): return jsonify(registry.create_room(request.get_json(force=True))), 201
    @app.get("/api/rooms/<room_id>")
    def get_room(room_id): return jsonify(registry.get_room(room_id))
    @app.post("/api/rooms/<room_id>/members")
    def join(room_id): return jsonify(registry.join(room_id, request.get_json(force=True)))
    @app.get("/api/rooms/<room_id>/members")
    def members(room_id): return jsonify(registry.list_members(room_id))
    @app.post("/api/rooms/<room_id>/members/<node_id>/heartbeat")
    def heartbeat(room_id, node_id): registry.heartbeat(room_id, node_id); return "", 204
    @app.delete("/api/rooms/<room_id>/members/<node_id>")
    def leave(room_id, node_id): registry.leave(room_id, node_id); return "", 204
    return app
