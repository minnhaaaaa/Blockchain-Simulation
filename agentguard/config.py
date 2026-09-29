from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class ConfigError(ValueError):
    pass


def _required(data: Mapping[str, Any], name: str, expected: type):
    value = data.get(name)
    if not isinstance(value, expected) or (expected is str and not value.strip()):
        raise ConfigError(f"{name} is required and must be {expected.__name__}")
    return value


def _positive_int(data: Mapping[str, Any], name: str) -> int:
    value = _required(data, name, int)
    if isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class SignallingConfig:
    bind_host: str
    bind_port: int
    database_path: Path
    membership_ttl_ms: int
    max_request_bytes: int

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SignallingConfig":
        port = _positive_int(data, "bind_port")
        if port > 65535:
            raise ConfigError("bind_port must be at most 65535")
        return cls(
            _required(data, "bind_host", str), port,
            Path(_required(data, "database_path", str)).expanduser().resolve(),
            _positive_int(data, "membership_ttl_ms"),
            _positive_int(data, "max_request_bytes"),
        )


@dataclass(frozen=True)
class ApplicationConfig:
    bind_host: str
    bind_port: int
    data_root: Path
    room_id: str
    node_id: str
    node_name: str
    advertised_host: str
    advertised_port: int
    signalling_url: str
    upload_limit_bytes: int
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ApplicationConfig":
        bind_port = _positive_int(data, "bind_port")
        advertised_port = _positive_int(data, "advertised_port")
        if max(bind_port, advertised_port) > 65535:
            raise ConfigError("ports must be at most 65535")
        origins = data.get("allowed_origins")
        if not isinstance(origins, Sequence) or isinstance(origins, (str, bytes)) or not origins:
            raise ConfigError("allowed_origins must be a non-empty sequence")
        if any(not isinstance(origin, str) or not origin for origin in origins):
            raise ConfigError("allowed_origins entries must be non-empty strings")
        return cls(
            _required(data, "bind_host", str), bind_port,
            Path(_required(data, "data_root", str)).expanduser().resolve(),
            _required(data, "room_id", str), _required(data, "node_id", str),
            _required(data, "node_name", str), _required(data, "advertised_host", str),
            advertised_port, _required(data, "signalling_url", str).rstrip("/"),
            _positive_int(data, "upload_limit_bytes"), tuple(origins),
        )
