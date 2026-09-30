import io
import secrets
import uuid

import pytest

from agentguard.auth import OperatorAuth
from agentguard.artifacts import ArtifactStore, ArtifactError


def test_generated_credentials_expire_and_logout(tmp_path):
    now = [0]
    path = tmp_path/"operator.key"
    auth = OperatorAuth(path, 10, clock=lambda:now[0])
    assert auth.login(secrets.token_urlsafe(32)) is None
    key = path.read_text()
    first = auth.login(key); second = auth.login(key)
    assert first["token"] != second["token"]
    assert auth.valid(first["token"])
    auth.logout(first["token"])
    assert not auth.valid(first["token"])
    assert auth.valid(second["token"])
    now[0] = 11
    assert not auth.valid(second["token"])
    assert OperatorAuth(path,10).login(key) is not None


def test_artifact_binding_is_atomic_and_does_not_move_bytes(tmp_path):
    store = ArtifactStore(tmp_path,10000)
    room = f"room-{uuid.uuid4()}"; content = secrets.token_bytes(40)
    first = store.store(room,"first.txt","text/plain",io.BytesIO(content))
    second = store.store(room,"second.txt","text/plain",io.BytesIO(content))
    other_job = str(uuid.uuid4()); target_job = str(uuid.uuid4())
    store.bind(room,[second["artifact_id"]],other_job)
    with pytest.raises(ArtifactError): store.bind(room,[first["artifact_id"],second["artifact_id"]],target_job)
    assert store._row(room,first["artifact_id"])["job_id"] is None
    store.bind(room,[first["artifact_id"]],target_job)
    assert store.read(room,target_job,first["artifact_id"]) == content
    assert store.read(room,other_job,second["artifact_id"]) == content
