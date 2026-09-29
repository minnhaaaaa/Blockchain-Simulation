"""Explicit production composition of the node, AgentGuard runtime and API."""
import threading
from dataclasses import dataclass
from pathlib import Path

from agentguard.artifacts import ArtifactStore
from agentguard.config import ApplicationConfig, ConfigError, _positive_int
from agentguard.policy import PolicyEvaluator
from agentguard.projection import ProjectionStore
from agentguard.providers import ManualProvider, ProviderRegistry
from agentguard.room_session import RoomSessionCoordinator
from agentguard.schema_validation import SchemaValidator
from agentguard.tools import default_registry
from agentguard.worker import AgentRuntime
from api.app import create_app
from consensus.pos.runtime import PosNodeRuntime, load_or_create_signer
from signalling.client import SignallingClient, SignallingClientError


def _section(config, name):
    value = config.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a configuration object")
    return value


class MembershipLoop:
    def __init__(self, client, runtime, node_id, interval_ms):
        self.client, self.runtime, self.node_id = client, runtime, node_id
        self.interval_seconds = interval_ms / 1000
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="room-membership", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.wait(self.interval_seconds):
            peer = self.runtime.peer
            if peer is None or peer.manifest is None:
                continue
            try:
                self.client.heartbeat(peer.room_id, self.node_id)
                members = self.client.members(peer.room_id)["items"]
                self.runtime.on_verified_room(peer.manifest, members)
            except (SignallingClientError, ValueError) as exc:
                # The room remains usable over existing sockets; the next
                # tick retries discovery. Never turn signalling into authority.
                print(f"membership refresh failed: {exc}")

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=self.interval_seconds + 1)
        peer = self.runtime.peer
        if peer is not None:
            try:
                self.client.leave(peer.room_id, self.node_id)
            except SignallingClientError:
                pass


@dataclass
class ComposedApplication:
    app: object
    runtime: AgentRuntime
    node_runtime: PosNodeRuntime
    membership: MembershipLoop

    def close(self):
        self.membership.stop()
        self.runtime.close()
        self.node_runtime.stop()


def compose(config: dict) -> ComposedApplication:
    application = ApplicationConfig.from_mapping(_section(config, "application"))
    node = _section(config, "node")
    agent = _section(config, "agent")
    discovery = _section(config, "signalling")
    schemas = SchemaValidator(Path(__file__).resolve().parents[1] / "contracts" / "schemas")
    if "stake_amount" in node and node["stake_amount"] is not None:
        _positive_int(node, "stake_amount")
    signer = load_or_create_signer(str(application.data_root), application.node_id)
    node_runtime = PosNodeRuntime(
        data_root=str(application.data_root), node_id=application.node_id,
        node_name=application.node_name, bind_host=application.advertised_host,
        bind_port=application.advertised_port, signer=signer,
        max_event_bytes=_positive_int(node, "max_event_bytes"),
        connect_timeout_s=_positive_int(node, "connect_timeout_s"),
        transition_timeout_s=_positive_int(node, "transition_timeout_s"),
        stake_amount=node.get("stake_amount"),
    )
    try:
        data_path = application.data_root / application.node_id
        artifacts = ArtifactStore(data_path / "artifacts", application.upload_limit_bytes)
        projections = ProjectionStore(data_path / "projection.sqlite3")
        tools = default_registry(_positive_int(agent, "max_csv_rows"), _positive_int(agent, "max_query_rows"))
        policy = PolicyEvaluator(schemas, _positive_int(agent, "max_schema_nodes"), _positive_int(agent, "max_schema_depth"))
        configured_providers = config.get("providers")
        if not isinstance(configured_providers, list):
            raise ConfigError("providers must be a list, which may be empty")
        providers = []
        provider_ids = set()
        for item in configured_providers:
            if not isinstance(item, dict) or item.get("kind") != "manual" or not item.get("provider_id") or not item.get("label"):
                raise ConfigError("each configured provider needs kind=manual, provider_id, and label")
            if item["provider_id"] in provider_ids:
                raise ConfigError("provider_id values must be unique")
            provider_ids.add(item["provider_id"])
            providers.append(ManualProvider(item["provider_id"], item["label"]))
        registry = ProviderRegistry(providers)
        client = SignallingClient(application.signalling_url, _positive_int(discovery, "timeout_seconds"))
        session = RoomSessionCoordinator(
            client, schemas, signer, application.node_id, application.node_name,
            application.advertised_host, application.advertised_port,
            on_verified_room=node_runtime.on_verified_room,
        )
        runtime = AgentRuntime(application.room_id, data_path / "work", signer, node_runtime.service,
                               schemas, artifacts, policy, tools, registry, projections)
        app = create_app(application, runtime, node_runtime.service, artifacts, projections, registry, tools, session)
        session.add_listener(lambda manifest, _members: runtime.rebuild_from_node(manifest["room_id"]))
        membership = MembershipLoop(client, node_runtime, application.node_id,
                                    _positive_int(discovery, "refresh_interval_ms"))
        return ComposedApplication(app, runtime, node_runtime, membership)
    except Exception:
        node_runtime.stop()
        raise
