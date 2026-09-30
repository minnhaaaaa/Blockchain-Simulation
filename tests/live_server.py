"""Start a real network for browser verification with generated test identities."""
import argparse
import json
from pathlib import Path
import signal
import tempfile
import threading

from scripts.live_demo import LiveNetwork, write_private
from tests.live_support import live_profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready-file",type=Path,required=True)
    args=parser.parse_args()
    network=LiveNetwork(live_profile(tempfile.mkdtemp(prefix="agentguard-live-test-")))
    stopped=threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig,lambda *_:stopped.set())
    try:
        write_private(args.ready_file,json.loads(network.access_path.read_text()))
        print(f"Live browser verification at {network.ui_origin}; private connection file at {args.ready_file}",flush=True)
        stopped.wait()
    finally: network.close()


if __name__ == "__main__": main()
