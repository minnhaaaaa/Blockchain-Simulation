"""Protocol fixtures are isolated to tests. Production has no canned model path."""
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from agentguard.providers import OpenAICompatibleProvider, ProviderError
from tests.test_runtime_api import RuntimeApiTests


@pytest.fixture
def configured(tmp_path):
    config = {"base_url": "https://model.example/v1", "model": "operator-model", "api_key": "test-secret",
              "timeout_seconds": 2, "max_context_bytes": 200000, "max_response_bytes": 100000,
              "job_limits": {"max_actions": 3, "max_runtime_ms_per_action": 1000, "max_output_bytes_per_action": 10000}}
    path = tmp_path / "provider.json"
    path.write_text(json.dumps(config))
    return OpenAICompatibleProvider("test-ai", "Test AI", str(path)), config, path


def test_configuration_is_private_and_missing_config_is_not_ready(tmp_path):
    provider = OpenAICompatibleProvider("test", "AI", str(tmp_path / "missing"))
    assert provider.state() == "misconfigured"
    with pytest.raises(ProviderError, match="server-only"):
        provider.chat([], [])


@pytest.mark.parametrize("url", ["http://external.example/v1", "https://user:secret@example.org", "https://example.org?key=secret", "file:///tmp/model"])
def test_insecure_or_credential_urls_rejected(configured, url):
    provider, config, path = configured; config["base_url"] = url; path.write_text(json.dumps(config))
    assert provider.state() == "misconfigured"


def test_chat_protocol_and_redacted_error(configured, monkeypatch):
    provider, config, _ = configured
    response = Mock(); response.status_code = 200
    response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "actual upstream answer"}}]}).encode()]
    post = Mock(return_value=response); monkeypatch.setattr(requests, "post", post)
    assert provider.chat([{"role": "user", "content": "question"}], [])["content"] == "actual upstream answer"
    assert post.call_args.args[0] == config["base_url"] + "/chat/completions"
    assert post.call_args.kwargs["allow_redirects"] is False
    assert json.loads(post.call_args.kwargs["data"])["model"] == config["model"]
    response.status_code = 401
    with pytest.raises(ProviderError, match="HTTP 401") as error:
        provider.chat([], [])
    assert "test-secret" not in str(error.value)


@pytest.fixture
def app(configured):
    fixture = RuntimeApiTests(); fixture.setUp()
    provider, _, _ = configured; fixture.providers._items[provider.provider_id] = provider
    yield fixture, provider
    fixture.runtime.close(); fixture.tearDown()


def call(name, arguments):
    return {"tool_calls": [{"id": "upstream-id", "function": {"name": name, "arguments": json.dumps(arguments)}}]}


def test_parallel_model_requests_stop_at_approval_boundary(app, monkeypatch):
    fixture, provider = app; job_id = create(app)
    first = call("report__write", {"name": "first.txt", "format": "text", "content": "first"})
    second = call("report__write", {"name": "second.txt", "format": "text", "content": "second"})
    monkeypatch.setattr(provider, "chat", lambda *_: {"tool_calls": first["tool_calls"] + second["tool_calls"]})
    response = fixture.client.post(f"/api/jobs/{job_id}/run")
    assert response.status_code == 202
    detail = fixture.client.get(f"/api/jobs/{job_id}").get_json()
    assert detail["job"]["pending_approval_count"] == 1
    proposals = [e for e in detail["events"] if e["event_type"] == "action.proposed"]
    assert len(proposals) == 1 and proposals[0]["payload"]["arguments"]["name"] == "first.txt"
    assert not any(e["event_type"] == "action.completed" for e in detail["events"])


def test_parallel_reads_are_serialized_and_budget_bounded(app, monkeypatch):
    fixture, provider = app
    uploaded = fixture.client.post("/api/artifacts", data={"file": (io.BytesIO(b"serial reads"), "input.txt")}).get_json()
    job_id = create(app, [uploaded["artifact_id"]]); rounds = []
    def chat(messages, tools):
        rounds.append(messages)
        if len(rounds) == 1:
            return {"tool_calls": call("artifact__hash", {"artifact_id": uploaded["artifact_id"]})["tool_calls"] * 4}
        assert not tools  # configured fixture allows only three actions
        return {"content": "Read within the action budget."}
    monkeypatch.setattr(provider, "chat", chat)
    response = fixture.client.post(f"/api/jobs/{job_id}/run")
    assert response.status_code == 202
    events = fixture.client.get(f"/api/jobs/{job_id}").get_json()["events"]
    actions = [e["payload"] for e in events if e["event_type"] == "action.proposed"]
    assert [action["action_sequence"] for action in actions] == [0, 1, 2]
    assert len({action["action_id"] for action in actions}) == 3


def create(app, inputs=None):
    fixture, provider = app
    response = fixture.client.post("/api/prompt-jobs", json={"instructions": "Work on my inputs", "provider_id": provider.provider_id, "input_artifact_ids": inputs or []})
    assert response.status_code == 202, response.get_json()
    return response.get_json()["job_id"]


def test_prompt_reads_real_tool_result_and_finishes(app, monkeypatch):
    fixture, provider = app
    data = b"User-owned input, not model output"
    uploaded = fixture.client.post("/api/artifacts", data={"file": (io.BytesIO(data), "input.txt")}).get_json()
    job_id = create(app, [uploaded["artifact_id"]]); messages_seen = []
    def chat(messages, tools):
        messages_seen.append(messages)
        if len(messages_seen) == 1:
            return call("artifact__hash", {"artifact_id": uploaded["artifact_id"]})
        digest = json.loads(messages[-1]["content"])["value"]["sha256"]
        assert digest == hashlib.sha256(data).hexdigest()
        return {"content": digest}
    monkeypatch.setattr(provider, "chat", chat)
    response = fixture.client.post(f"/api/jobs/{job_id}/run")
    assert response.status_code == 202, response.get_json()
    assert response.get_json()["state"] == "completed"
    detail = fixture.client.get(f"/api/jobs/{job_id}").get_json()
    assert detail["job"]["status"] == "completed"
    assert detail["events"][-1]["payload"]["summary"] == hashlib.sha256(data).hexdigest()
    assert len(messages_seen) == 2
    assert fixture.client.post(f"/api/jobs/{job_id}/run").status_code == 409


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_agent_pauses_for_write_and_resumes_once(app, monkeypatch, decision):
    fixture, provider = app; job_id = create(app); rounds = []
    def chat(messages, tools):
        rounds.append(messages)
        if len(rounds) == 1:
            return call("report__write", {"name": "report.txt", "format": "text", "content": "Review this output"})
        assert messages[-1]["role"] == "tool"
        return {"content": "Write approved." if decision == "approved" else "Write rejected; no file was created."}
    monkeypatch.setattr(provider, "chat", chat)
    assert fixture.client.post(f"/api/jobs/{job_id}/run").status_code == 202
    events = fixture.runtime._events(job_id)
    assert events[-1]["event_type"] == "action.approval_required"
    assert not any(e["event_type"] == "action.completed" for e in events)
    assert fixture.client.post(f"/api/jobs/{job_id}/run").status_code == 202
    assert len(rounds) == 1
    action_id = events[-1]["payload"]["action_id"]
    assert fixture.client.post(f"/api/jobs/{job_id}/actions/{action_id}/decision", json={"decision": decision}).status_code == 202
    assert fixture.client.post(f"/api/jobs/{job_id}/run").status_code == 202
    assert sum(e["event_type"] == "action.completed" for e in fixture.runtime._events(job_id)) == (1 if decision == "approved" else 0)


def test_invalid_call_does_not_execute(app, monkeypatch):
    fixture, provider = app; job_id = create(app)
    monkeypatch.setattr(provider, "chat", lambda *_: call("shell__exec", {"command": "anything"}))
    assert fixture.client.post(f"/api/jobs/{job_id}/run").status_code == 409
    assert not any(e["event_type"] == "action.proposed" for e in fixture.runtime._events(job_id))


def test_missing_limits_and_invalid_prompt_rejected_before_job(app, configured):
    fixture, provider = app; _, config, path = configured
    config.pop("job_limits"); path.write_text(json.dumps(config))
    response = fixture.client.post("/api/prompt-jobs", json={"instructions": "task", "provider_id": provider.provider_id})
    assert response.status_code == 422
    assert fixture.client.get("/api/jobs").get_json()["items"] == []
    assert fixture.client.post("/api/prompt-jobs", json={"instructions": "  "}).status_code == 422
