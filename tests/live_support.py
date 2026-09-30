"""Explicit test configuration, never imported by the application or launcher."""
import uuid


def live_profile(root):
    return {
        "host": "127.0.0.1", "state_root": str(root), "protocol_version": "1",
        "provider_label": f"Operator {uuid.uuid4().hex[:8]}",
        "nodes": [{"name": f"Node {uuid.uuid4().hex[:8]}", "balance": 1000, "stake": 50 if index == 0 else 0} for index in range(3)],
        "consensus_parameters": {"epoch_ms": 600, "max_clock_skew_ms": 60000, "finality_depth": 1,
                                 "max_connections": 8, "block_reward": 0, "minimum_stake": 1},
        "node": {"max_event_bytes": 500000, "connect_timeout_s": 5, "transition_timeout_s": 30},
        "agent": {"max_csv_rows": 50000, "max_query_rows": 5000, "max_schema_nodes": 1000, "max_schema_depth": 20},
        "signalling": {"membership_ttl_ms": 15000, "max_request_bytes": 1000000, "timeout_seconds": 5, "refresh_interval_ms": 1000},
        "upload_limit_bytes": 10000000, "session_ttl_seconds": 3600, "poll_interval_ms": 1000,
    }
