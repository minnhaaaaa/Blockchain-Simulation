"""Real HTTP/P2P/tool integration against a test-only compatible protocol server.

This verifies transport and signed execution, not the quality of a hosted model.
"""
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.live_demo import LiveNetwork
from tests.live_support import live_profile


def test_compatible_http_tool_loop_finalizes_on_all_nodes(tmp_path):
    calls = []
    artifact_id = None
    content = secrets.token_bytes(48)
    expected = hashlib.sha256(content).hexdigest()
    class Endpoint(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            assert self.path == "/v1/chat/completions"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body)
            if len(calls) == 1:
                message = {"role": "assistant", "content": None, "tool_calls": [{"id": "test-call",
                    "type": "function", "function": {"name": "artifact__hash", "arguments": json.dumps({"artifact_id": artifact_id})}}]}
                reason = "tool_calls"
            else:
                value = json.loads(body["messages"][-1]["content"])["value"]
                message = {"role": "assistant", "content": value["sha256"]}; reason = "stop"
            data = json.dumps({"choices": [{"message": message, "finish_reason": reason}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Endpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    config = tmp_path / "test-only-provider.json"
    config.write_text(json.dumps({"base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "protocol-test",
        "api_key": secrets.token_urlsafe(), "timeout_seconds": 5, "max_context_bytes": 200000,
        "max_response_bytes": 100000, "job_limits": {"max_actions": 3,
        "max_runtime_ms_per_action": 5000, "max_output_bytes_per_action": 100000}}))
    profile = live_profile(tmp_path / "network"); profile["agent_provider_config"] = str(config)
    network = None
    try:
        network = LiveNetwork(profile, frontend=False)
        node = network.nodes[0]; session = node["session"]; origin = node["apiOrigin"]
        response = session.post(origin + "/api/artifacts", files={"file": ("input.bin", content)}, timeout=5)
        assert response.status_code == 201; artifact_id = response.json()["artifact_id"]
        providers = session.get(origin + "/api/providers", timeout=5).json()["items"]
        provider = next(item for item in providers if item["kind"] == "openai_compatible")
        assert provider["state"] == "ready"
        response = session.post(origin + "/api/prompt-jobs", json={"instructions": "Hash my input", "provider_id": provider["provider_id"], "input_artifact_ids": [artifact_id]}, timeout=5)
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        run = session.post(origin + f"/api/jobs/{job_id}/run", timeout=10)
        assert run.status_code == 202, run.text
        assert len(calls) == 2
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            details = [peer["session"].get(peer["apiOrigin"] + f"/api/jobs/{job_id}", timeout=5).json() for peer in network.nodes]
            if all(detail.get("job", {}).get("finality") == "finalized" for detail in details): break
            time.sleep(.1)
        for detail in details:
            assert detail["job"]["status"] == "completed"
            assert detail["job"]["finality"] == "finalized"
            assert detail["events"][-1]["payload"]["summary"] == expected
    finally:
        if network: network.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
