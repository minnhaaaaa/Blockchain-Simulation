import argparse
import json

from signalling.app import create_app
from agentguard.config import SignallingConfig


def main():
    parser=argparse.ArgumentParser(description="AgentGuard room signalling service")
    parser.add_argument("--config",required=True,help="Path to an explicit signalling JSON configuration")
    args=parser.parse_args()
    with open(args.config,"r",encoding="utf-8") as handle: config=SignallingConfig.from_mapping(json.load(handle))
    create_app(config).run(host=config.bind_host,port=config.bind_port)


if __name__=="__main__": main()
