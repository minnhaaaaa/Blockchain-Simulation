import socket
import uuid

from api.compose import compose


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_real_api_composition_starts_unconfigured_and_closes(tmp_path):
    config = {
        "application": {
            "bind_host": "127.0.0.1", "bind_port": _free_port(),
            "data_root": str(tmp_path), "room_id": "operator-room",
            "node_id": str(uuid.uuid4()), "node_name": "operator-node",
            "advertised_host": "127.0.0.1", "advertised_port": _free_port(),
            "signalling_url": "http://127.0.0.1:1", "upload_limit_bytes": 100000,
            "allowed_origins": ["http://127.0.0.1:2"],
        },
        "node": {"max_event_bytes": 100000, "connect_timeout_s": 2,
                 "transition_timeout_s": 3, "stake_amount": None},
        "agent": {"max_csv_rows": 100, "max_query_rows": 100,
                  "max_schema_nodes": 100, "max_schema_depth": 10},
        "signalling": {"timeout_seconds": 2, "refresh_interval_ms": 1000},
        "providers": [],
    }
    composed = compose(config)
    try:
        status = composed.app.test_client().get("/api/status")
        assert status.status_code == 200
        assert status.get_json()["provider_state"] == "unconfigured"
    finally:
        composed.close()
