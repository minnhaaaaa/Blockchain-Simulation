import json
import re
import uuid
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


class SchemaValidator:
    """Small Draft 2020-12 subset used by the committed contracts."""

    def __init__(self, schema_root: Path):
        self.schema_root = schema_root.resolve()
        self._cache: dict[Path, dict] = {}

    def load(self, name: str) -> dict:
        path = (self.schema_root / name).resolve()
        if path.parent != self.schema_root or not path.is_file():
            raise SchemaValidationError("$schema", "unknown schema")
        if path not in self._cache:
            self._cache[path] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[path]

    def validate_named(self, name: str, value: Any) -> None:
        self._validate(value, self.load(name), "$", (self.schema_root / name).resolve())

    def validate_fragment(self, schema: dict, value: Any) -> None:
        self._validate(value, schema, "$", None)

    def _resolve(self, ref: str, current: Path | None) -> tuple[dict, Path | None]:
        file_part, _, fragment = ref.partition("#")
        if file_part:
            base = current.parent if current else self.schema_root
            target = (base / file_part).resolve()
            if target.parent != self.schema_root:
                raise SchemaValidationError("$ref", "reference escapes schema root")
            schema = self._cache.setdefault(target, json.loads(target.read_text(encoding="utf-8")))
            current = target
        elif current:
            schema = self._cache.setdefault(current, json.loads(current.read_text(encoding="utf-8")))
        else:
            raise SchemaValidationError("$ref", "local reference lacks document")
        if fragment:
            for part in fragment.lstrip("/").split("/"):
                schema = schema[part.replace("~1", "/").replace("~0", "~")]
        return schema, current

    def _matches(self, value: Any, schema: dict, current: Path | None) -> bool:
        try:
            self._validate(value, schema, "$", current)
            return True
        except SchemaValidationError:
            return False

    def _validate(self, value: Any, schema: dict, path: str, current: Path | None) -> None:
        if "$ref" in schema:
            resolved, document = self._resolve(schema["$ref"], current)
            self._validate(value, resolved, path, document)
            return
        if "const" in schema and value != schema["const"]:
            raise SchemaValidationError(path, f"must equal {schema['const']!r}")
        if "enum" in schema and value not in schema["enum"]:
            raise SchemaValidationError(path, "is not an allowed value")
        if "allOf" in schema:
            for item in schema["allOf"]:
                self._validate(value, item, path, current)
        if "anyOf" in schema:
            # was silently ignored, which made every `not: {anyOf: ...}` (e.g. a join request) fail
            if not any(self._matches(value, item, current) for item in schema["anyOf"]):
                raise SchemaValidationError(path, "must match at least one alternative")
        if "oneOf" in schema:
            if sum(self._matches(value, item, current) for item in schema["oneOf"]) != 1:
                raise SchemaValidationError(path, "must match exactly one alternative")
        if "not" in schema and self._matches(value, schema["not"], current):
            raise SchemaValidationError(path, "matches a forbidden schema")
        if "if" in schema and self._matches(value, schema["if"], current):
            self._validate(value, schema.get("then", {}), path, current)
        expected = schema.get("type")
        type_ok = {
            "object": isinstance(value, dict), "array": isinstance(value, list),
            "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool), "null": value is None,
        }
        if expected and not type_ok.get(expected, False):
            raise SchemaValidationError(path, f"must be {expected}")
        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    raise SchemaValidationError(path, f"missing required field {name}")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                unknown = set(value) - set(properties)
                if unknown:
                    raise SchemaValidationError(path, f"unknown fields: {sorted(unknown)}")
            for name, item in value.items():
                if name in properties:
                    self._validate(item, properties[name], f"{path}.{name}", current)
        elif isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                raise SchemaValidationError(path, "has too few items")
            if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
                raise SchemaValidationError(path, "items must be unique")
            if "items" in schema:
                for index, item in enumerate(value):
                    self._validate(item, schema["items"], f"{path}[{index}]", current)
        elif isinstance(value, str):
            if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", len(value)):
                raise SchemaValidationError(path, "has invalid length")
            if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
                raise SchemaValidationError(path, "has invalid format")
            if schema.get("format") == "uuid":
                try: uuid.UUID(value)
                except ValueError as exc: raise SchemaValidationError(path, "must be UUID") from exc
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < schema.get("minimum", value) or value > schema.get("maximum", value):
                raise SchemaValidationError(path, "is outside allowed range")
