from dataclasses import dataclass
from typing import Protocol
import json
from pathlib import Path
from urllib.parse import urlsplit
import requests


class ProviderError(RuntimeError): pass


class Provider(Protocol):
    provider_id: str
    label: str
    kind: str
    def state(self) -> str: ...
    def propose(self, job: dict, events: list[dict], tools: list[dict]) -> dict: ...


@dataclass
class ManualProvider:
    provider_id: str
    label: str
    kind: str = "manual"
    def state(self): return "ready"
    def propose(self, job, events, tools):
        raise ProviderError("manual provider requires an action submitted through the API")


@dataclass
class OpenAICompatibleProvider:
    """Server-only Chat Completions connection. Configuration is reloaded per call."""
    provider_id: str
    label: str
    config_path: str
    kind: str = "openai_compatible"

    def settings(self):
        try:
            config = json.loads(Path(self.config_path).read_text())
            for key in ("base_url", "model", "api_key"):
                if not isinstance(config[key], str) or not config[key].strip():
                    raise ValueError(key)
            url = urlsplit(config["base_url"])
            if url.username or url.password or url.query or url.fragment or not url.hostname:
                raise ValueError("URL")
            if url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")):
                raise ValueError("HTTPS required except loopback")
            for key in ("timeout_seconds", "max_context_bytes", "max_response_bytes"):
                if type(config[key]) is not int or config[key] <= 0:
                    raise ValueError(key)
            return config
        except (OSError, ValueError, KeyError, TypeError):
            raise ProviderError("Configure the server-only agent-provider.local.json file: URL, model, key and limits are required.") from None

    def state(self):
        try:
            self.settings()
            return "ready"
        except ProviderError:
            return "misconfigured"

    def chat(self, messages, tools):
        config = self.settings()
        body = {"model": config["model"], "messages": messages, "stream": False}
        if tools:
            body.update(tools=tools, parallel_tool_calls=False)
        encoded = json.dumps(body).encode()
        if len(encoded) > config["max_context_bytes"]:
            raise ProviderError("Agent context exceeds the configured byte limit. Use smaller inputs or adjust the server limit.")
        try:
            # No redirects: never forward a credential to a different endpoint.
            with requests.post(config["base_url"].rstrip("/") + "/chat/completions",
                               headers={"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"},
                               data=encoded, timeout=config["timeout_seconds"], allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise ProviderError(f"Agent endpoint returned HTTP {response.status_code}. Check server configuration and account access.")
                chunks = []; size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > config["max_response_bytes"]:
                        raise ProviderError("Agent response exceeds the configured byte limit.")
                    chunks.append(chunk)
                choice = json.loads(b"".join(chunks))["choices"][0]
                if choice.get("finish_reason") not in ("stop", "tool_calls"):
                    raise ProviderError("Agent response was interrupted or refused; no action was executed.")
                message = choice["message"]
                if not isinstance(message, dict):
                    raise ValueError("message")
                return message
        except requests.RequestException:
            raise ProviderError("Could not reach the agent endpoint. Check its URL, TLS and timeout settings.") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("Agent endpoint returned an invalid Chat Completions response.") from None


class ProviderRegistry:
    def __init__(self, providers: list[Provider]): self._items={p.provider_id:p for p in providers}
    def get(self, provider_id):
        if provider_id not in self._items: raise ProviderError("provider is not configured")
        return self._items[provider_id]
    def public(self):
        return [{"provider_id":p.provider_id,"label":p.label,"kind":p.kind,"state":p.state()}
                for p in self._items.values()]
