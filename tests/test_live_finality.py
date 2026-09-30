"""Real HTTP + P2P regression: quiet rooms must finalize on every peer."""
import time
import uuid
import secrets
import hashlib
from canonical import canonical_json

from scripts.live_demo import LiveNetwork
from tests.live_support import live_profile


def test_empty_successors_reach_all_peers_and_finalize_last_event(tmp_path):
    network = LiveNetwork(live_profile(tmp_path), frontend=False)
    try:
        owner = network.nodes[0]
        response = owner["session"].post(owner["apiOrigin"] + "/api/jobs", json={
            "title": str(uuid.uuid4()), "instructions": str(uuid.uuid4()),
            "provider_id": network.composed[0].runtime.providers.public()[0]["provider_id"],
            "input_artifact_ids": [],
            "policy": {"rules": [{"tool_id": "report.write", "effect": "deny", "read_artifact_ids": [],
                                    "write_scopes": [], "argument_constraints": {}}],
                       "limits": {"max_actions": 1, "max_runtime_ms_per_action": 1000,
                                               "max_output_bytes_per_action": 1000}}
        }, timeout=5)
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        deadline = time.monotonic() + 20
        states = []
        while time.monotonic() < deadline:
            states = []
            for node in network.nodes:
                result = node["session"].get(node["apiOrigin"] + f"/api/jobs/{job_id}", timeout=5)
                states.append(result.json().get("job", {}).get("finality"))
            if all(state == "finalized" for state in states):
                break
            time.sleep(.1)
        assert states == ["finalized"] * len(network.nodes)
    finally:
        network.close()


def test_real_csv_query_and_reviewed_report_download(tmp_path):
    profile = live_profile(tmp_path)
    profile["agent"].update(max_csv_rows=3, max_query_rows=1)
    network = LiveNetwork(profile, frontend=False)
    try:
        node = network.nodes[0]; session = node["session"]; origin = node["apiOrigin"]
        amounts = [secrets.randbelow(10000) for _ in range(3)]
        content = "amount\n" + "\n".join(str(value) for value in amounts)
        upload = session.post(origin + "/api/artifacts", files={"file": (f"{uuid.uuid4()}.csv", content, "text/csv")}, timeout=5)
        assert upload.status_code == 201, upload.text
        aid = upload.json()["artifact_id"]
        provider = session.get(origin + "/api/providers", timeout=5).json()["items"][0]["provider_id"]
        rules = [{"tool_id": tool, "effect": effect, "read_artifact_ids": reads,
                  "write_scopes": writes, "argument_constraints": {}}
                 for tool, effect, reads, writes in [
                     ("csv.import_sqlite", "allow", [aid], ["job.database"]),
                     ("sql.query_readonly", "allow", [], []),
                     ("report.write", "approval_required", [], ["job.outputs"])]]
        response = session.post(origin + "/api/jobs", json={"title": str(uuid.uuid4()), "instructions": str(uuid.uuid4()),
            "provider_id": provider, "input_artifact_ids": [aid], "policy": {"rules": rules,
            "limits": {"max_actions": 3, "max_runtime_ms_per_action": 5000, "max_output_bytes_per_action": 100000}}}, timeout=5)
        assert response.status_code == 202, response.text
        base = origin + "/api/jobs/" + response.json()["job_id"]
        assert session.post(base + "/accept", timeout=5).status_code == 202
        table = "t_" + uuid.uuid4().hex
        def propose(tool, args, inputs, output):
            result = session.post(base + "/manual-actions", json={"tool_id": tool, "arguments": args,
                "input_artifact_ids": inputs, "expected_output_kind": output}, timeout=5)
            assert result.status_code == 202, result.text
        propose("csv.import_sqlite", {"artifact_id": aid, "table_name": table}, [aid], "table")
        propose("sql.query_readonly", {"query": f'SELECT SUM(CAST(amount AS INTEGER)) AS total FROM "{table}"', "max_rows": 1}, [], "table")
        detail = session.get(base, timeout=5).json()
        receipt = [e["payload"] for e in detail["events"] if e["event_type"] == "action.completed"][-1]
        assert receipt["status"] == "success", receipt
        result = session.get(base + "/artifacts/" + receipt["output_artifacts"][0]["artifact_id"], timeout=5)
        assert result.json() == {"columns": ["total"], "rows": [[sum(amounts)]]}
        # Model reports commonly contain Unicode punctuation and non-English text.
        # Their request hash must use the consensus encoder, not ASCII-escaped JSON.
        report = f"Computed total: {sum(amounts)} — résumé • नमस्ते 🔒"
        propose("report.write", {"name": f"{uuid.uuid4()}.txt", "format": "text", "content": report}, [], "artifact")
        detail = session.get(base, timeout=5).json()
        action = [e["payload"] for e in detail["events"] if e["event_type"] == "action.proposed"][-1]
        assert detail["action_scopes"][action["action_id"]] == ["job.outputs"]
        approved = session.post(base + "/actions/" + action["action_id"] + "/decision", json={"decision": "approved"}, timeout=5)
        assert approved.status_code == 202, approved.text
        detail = session.get(base, timeout=5).json()
        receipt = [e["payload"] for e in detail["events"] if e["event_type"] == "action.completed"][-1]
        assert receipt["status"] == "success", receipt
        output = session.get(base + "/artifacts/" + receipt["output_artifacts"][0]["artifact_id"], timeout=5)
        assert output.text == report
        assert receipt["request_hash"] == hashlib.sha256(canonical_json(action)).hexdigest()
        # The real peers must also accept the Unicode action's completion receipt.
        job_id = action["job_id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            replicated = [peer["session"].get(peer["apiOrigin"] + f"/api/jobs/{job_id}", timeout=5).json()
                          for peer in network.nodes]
            if all(any(e["event_type"] == "action.completed" and e["payload"]["receipt_id"] == receipt["receipt_id"]
                       for e in result.get("events", [])) for result in replicated):
                break
            time.sleep(.1)
        assert all(any(e["event_type"] == "action.completed" and e["payload"]["receipt_id"] == receipt["receipt_id"]
                       for e in result.get("events", [])) for result in replicated)
    finally:
        network.close()
