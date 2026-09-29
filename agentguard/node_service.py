from dataclasses import dataclass
from typing import Callable, Protocol


class NodeUnavailable(RuntimeError): pass
class SubmissionRejected(ValueError): pass


@dataclass(frozen=True)
class Submission:
    submission_id: str
    event_id: str
    ledger_state: str
    event_hash: str | None

    def to_dict(self): return self.__dict__.copy()


class NodeService(Protocol):
    def submit_event(self, event: dict) -> Submission: ...
    def get_event(self, event_id: str) -> dict | None: ...
    def list_job_events(self, job_id: str) -> list[dict]: ...
    def get_chain_summary(self, limit: int) -> dict: ...
    def get_block(self, block_id: str) -> dict | None: ...
    def get_peer_summaries(self) -> list[dict]: ...
    def get_stake_snapshot(self) -> dict: ...
    def subscribe_state_changes(self, callback: Callable[[dict], None]) -> Callable[[], None]: ...

