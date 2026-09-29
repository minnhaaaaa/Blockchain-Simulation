import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class SignallingClientError(RuntimeError): pass


class SignallingClient:
    def __init__(self, base_url: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base_url + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SignallingClientError(str(exc)) from exc

    def create_room(self, manifest): return self._request("POST", "/api/rooms", manifest)
    def get_room(self, room_id): return self._request("GET", f"/api/rooms/{quote(room_id)}")
    def join(self, room_id, member): return self._request("POST", f"/api/rooms/{quote(room_id)}/members", member)
    def members(self, room_id): return self._request("GET", f"/api/rooms/{quote(room_id)}/members")
    def heartbeat(self, room_id, node_id): return self._request("POST", f"/api/rooms/{quote(room_id)}/members/{quote(node_id)}/heartbeat")
    def leave(self, room_id, node_id): return self._request("DELETE", f"/api/rooms/{quote(room_id)}/members/{quote(node_id)}")
