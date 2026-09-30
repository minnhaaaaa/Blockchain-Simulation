"""Launch real signalling, PoS nodes, authenticated APIs and the React UI.

All operational settings come from an operator profile. Identities, room ID,
credentials and ports are generated. No jobs, files, events or results are seeded.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

import requests
from werkzeug.serving import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.compose import compose
from agentguard.config import SignallingConfig
from signalling.app import create_app as signalling_app


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        if isinstance(code, int) and code >= 400:
            super().log_request(code, size)


def free_port(host):
    with socket.socket() as connection:
        connection.bind((host, 0))
        return connection.getsockname()[1]


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)


def configure(path):
    """Ask for every operational choice, without silently supplying values."""
    def text(label):
        while True:
            value = input(f"{label}: ").strip()
            if value:
                return value
    def number(label, minimum=1):
        while True:
            try:
                value = int(text(label))
                if value >= minimum:
                    return value
            except ValueError:
                pass
            print(f"Enter an integer >= {minimum}.")
    profile = {"host": text("Local bind host"), "state_root": text("Directory for persistent runs"),
               "protocol_version": text("Room protocol version"), "provider_label": text("Manual provider display name"),
               "nodes": []}
    for index in range(number("Number of nodes")):
        profile["nodes"].append({"name": text(f"Node {index+1} name"), "balance": number("Genesis balance"), "stake": number("Validator stake (0 for an observer)", 0)})
    profile["consensus_parameters"] = {name: number(name, minimum) for name, minimum in
        [("epoch_ms",100),("max_clock_skew_ms",0),("finality_depth",1),("max_connections",1),("block_reward",0),("minimum_stake",1)]}
    for section, fields in {
        "node": ["max_event_bytes", "connect_timeout_s", "transition_timeout_s"],
        "agent": ["max_csv_rows", "max_query_rows", "max_schema_nodes", "max_schema_depth"],
        "signalling": ["membership_ttl_ms", "max_request_bytes", "timeout_seconds", "refresh_interval_ms"]
    }.items():
        profile[section] = {name: number(name) for name in fields}
    profile["upload_limit_bytes"] = number("Upload size limit in bytes")
    profile["session_ttl_seconds"] = number("Operator session lifetime in seconds")
    profile["poll_interval_ms"] = number("Dashboard refresh interval in milliseconds", 1000)
    write_private(path, profile)
    print(f"Saved operator profile: {path}")


class LiveNetwork:
    def __init__(self, profile, *, frontend=True):
        self.profile = profile
        self.servers, self.composed = [], []
        self.frontend = None
        self.run_root = Path(profile["state_root"]).expanduser().resolve() / str(uuid.uuid4())
        self.run_root.mkdir(parents=True, mode=0o700)
        self.nodes = []
        try:
            self._start(frontend)
        except BaseException:
            self.close()
            raise

    def serve(self, app, host, port):
        server = make_server(host, port, app, threaded=True, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.servers.append((server, thread)); thread.start()

    def _start(self, frontend):
        p = self.profile; host = p["host"]
        if not p["nodes"] or not any(node["stake"] > 0 for node in p["nodes"]):
            raise ValueError("Configure at least one validator with positive stake.")
        if p["poll_interval_ms"] < 1000:
            raise ValueError("poll_interval_ms must be at least 1000")
        signal_port, ui_port = free_port(host), free_port(host)
        self.ui_origin = f"http://{host}:{ui_port}"
        signal_origin = f"http://{host}:{signal_port}"
        room_id = f"room-{uuid.uuid4()}"
        provider_id = str(uuid.uuid4())
        agent_provider_id = str(uuid.uuid4())
        signalling = SignallingConfig(host, signal_port, self.run_root/"rooms.sqlite3", p["signalling"]["membership_ttl_ms"], p["signalling"]["max_request_bytes"])
        self.serve(signalling_app(signalling), host, signal_port)
        for supplied in p["nodes"]:
            node_id = str(uuid.uuid4()); api_port = free_port(host); peer_port = free_port(host)
            config = {"application": {"bind_host":host, "bind_port":api_port, "advertised_host":host, "advertised_port":peer_port,
                "data_root":str(self.run_root), "room_id":room_id, "node_id":node_id, "node_name":supplied["name"],
                "signalling_url":signal_origin, "upload_limit_bytes":p["upload_limit_bytes"], "allowed_origins":[self.ui_origin]},
                "node": {**p["node"], "stake_amount":supplied["stake"] or None}, "agent":p["agent"],
                "signalling":p["signalling"], "auth":{"session_ttl_seconds":p["session_ttl_seconds"]},
                "providers":[{"kind":"manual", "provider_id":provider_id, "label":p["provider_label"]},
                             {"kind":"openai_compatible", "provider_id":agent_provider_id, "label":"AI agent",
                              "config_path":str(Path(p.get("agent_provider_config", ROOT / "agent-provider.local.json")).resolve())}]}
            write_private(self.run_root/f"{node_id}.config.json", config)
            node = compose(config); self.composed.append(node); self.serve(node.app,host,api_port)
            origin = f"http://{host}:{api_port}"
            key = (self.run_root/node_id/"operator.key").read_text().strip()
            session = requests.Session()
            login = session.post(f"{origin}/api/auth/login",json={"access_key":key},timeout=p["node"]["connect_timeout_s"])
            login.raise_for_status(); session.headers["Authorization"] = f'Bearer {login.json()["token"]}'
            self.nodes.append({"name":supplied["name"], "node_id":node_id, "apiOrigin":origin, "access_key":key,
                "public_key":node.runtime.signer.public_key_pem, "balance":supplied["balance"], "stake":supplied["stake"], "session":session})
        request = {"operation":"create", "room_id":room_id, "protocol_version":p["protocol_version"], "consensus_parameters":p["consensus_parameters"],
                   "genesis_allocations":[{"public_key":node["public_key"],"amount":node["balance"],"stake":node["stake"]} for node in self.nodes]}
        for index, node in enumerate(self.nodes):
            response=node["session"].post(f'{node["apiOrigin"]}/api/room-session',json=request if index==0 else {"operation":"join","room_id":room_id},timeout=p["node"]["transition_timeout_s"])
            if not response.ok:
                raise RuntimeError(f"Room setup failed: {response.text}")
        self.access_path = self.run_root/"operator-access.json"
        write_private(self.access_path,{"uiOrigin":self.ui_origin,"room_id":room_id,"pollIntervalMs":p["poll_interval_ms"],
            "nodes":[{k:v for k,v in node.items() if k!="session"} for node in self.nodes]})
        runtime_path=self.run_root/"public-runtime.json"
        write_private(runtime_path,{"pollIntervalMs":p["poll_interval_ms"],"nodes":[{"name":node["name"],"apiOrigin":node["apiOrigin"]} for node in self.nodes]})
        if frontend:
            executable=shutil.which("node")
            if executable is None: raise RuntimeError("Install Node.js or put its executable on PATH.")
            env={**os.environ,"AGENTGUARD_RUNTIME_FILE":str(runtime_path)}
            self.frontend=subprocess.Popen([executable,str(ROOT/"frontend/node_modules/vite/bin/vite.js"),"--host",host,"--port",str(ui_port),"--strictPort"],cwd=ROOT/"frontend",env=env)

    def close(self):
        if self.frontend:
            self.frontend.terminate()
            try: self.frontend.wait(timeout=5)
            except subprocess.TimeoutExpired: self.frontend.kill(); self.frontend.wait()
        for app in reversed(self.composed): app.close()
        for server, thread in reversed(self.servers): server.shutdown(); server.server_close(); thread.join(timeout=5)
        for node in self.nodes: node["session"].close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--configure",type=Path,help="Create an operator profile interactively (no preset values)")
    group.add_argument("--config",type=Path,help="Start a real network from your profile")
    parser.add_argument("--ready-file",type=Path,help="Write the private runtime access document here for live browser tests")
    args=parser.parse_args()
    if args.configure:
        configure(args.configure); return
    profile=json.loads(args.config.read_text())
    network=LiveNetwork(profile)
    stopped=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,lambda *_:stopped.set())
    try:
        if args.ready_file: write_private(args.ready_file,json.loads(network.access_path.read_text()))
        print(f"\nWorkspace: {network.ui_origin}\nOperator access: {network.access_path}\nNo jobs or input files have been created. Sign in to begin.\n",flush=True)
        while not stopped.wait(.5):
            if network.frontend and network.frontend.poll() is not None: raise RuntimeError("Frontend exited before the network stopped")
    finally: network.close()


if __name__ == "__main__": main()
