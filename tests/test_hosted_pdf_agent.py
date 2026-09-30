"""Opt-in, real OpenRouter PDF smoke test. Never part of offline CI.

Uses the operator's configured free model and a disposable real network. Synthetic
input is confined to this test; production contains no canned jobs or answers.
"""
import os
import uuid

import pytest

from scripts.live_demo import LiveNetwork, ROOT
from tests.live_support import live_profile
from tests.test_pdf_reader import pdf_bytes


@pytest.mark.skipif(os.getenv("CERTA_TEST_HOSTED_AGENT") != "1", reason="Explicit opt-in required for hosted model calls")
def test_real_free_model_reads_uploaded_pdf(tmp_path):
    profile = live_profile(tmp_path / "network")
    profile["agent_provider_config"] = str(ROOT / "agent-provider.local.json")
    token = str(uuid.uuid4())
    network = LiveNetwork(profile, frontend=False)
    try:
        node = network.nodes[0]; session = node["session"]; origin = node["apiOrigin"]
        artifact = session.post(origin + "/api/artifacts", files={"file": ("smoke.pdf", pdf_bytes(["Verification code: " + token, "Second page: the colour is silver."]), "application/pdf")}, timeout=10)
        assert artifact.status_code == 201
        providers = session.get(origin + "/api/providers", timeout=10).json()["items"]
        provider = next(p for p in providers if p["kind"] == "openai_compatible")
        created = session.post(origin + "/api/prompt-jobs", json={"provider_id": provider["provider_id"], "input_artifact_ids": [artifact.json()["artifact_id"]],
            "instructions": "Read both pages of the attached PDF using pdf.read. Return the verification code from page 1 and the colour from page 2. Do not create a report file."}, timeout=10)
        assert created.status_code == 202
        job_id = created.json()["job_id"]
        run = session.post(origin + f"/api/jobs/{job_id}/run", timeout=240)
        assert run.status_code == 202, run.text
        detail = session.get(origin + f"/api/jobs/{job_id}", timeout=10).json()
        assert detail["job"]["status"] == "completed"
        assert any(e["event_type"] == "action.proposed" and e["payload"]["tool_id"] == "pdf.read" for e in detail["events"])
        assert any(e["event_type"] == "action.completed" and e["payload"]["status"] == "success" for e in detail["events"])
        summary = detail["events"][-1]["payload"]["summary"]
        assert token in summary and "silver" in summary.lower()
    finally:
        network.close()
