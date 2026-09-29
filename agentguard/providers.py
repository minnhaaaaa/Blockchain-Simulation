from dataclasses import dataclass
from typing import Protocol


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


class ProviderRegistry:
    def __init__(self, providers: list[Provider]): self._items={p.provider_id:p for p in providers}
    def get(self, provider_id):
        if provider_id not in self._items: raise ProviderError("provider is not configured")
        return self._items[provider_id]
    def public(self):
        return [{"provider_id":p.provider_id,"label":p.label,"kind":p.kind,"state":p.state()}
                for p in self._items.values()]

