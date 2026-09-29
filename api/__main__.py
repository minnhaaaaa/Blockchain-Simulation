import argparse
import json

from api.compose import compose
from agentguard.config import ApplicationConfig


def main():
    parser = argparse.ArgumentParser(description="Run one AgentGuard node and its local API")
    parser.add_argument("--config", required=True, help="Path to explicit node/API JSON configuration")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    application = ApplicationConfig.from_mapping(config["application"])
    composed = compose(config)
    try:
        composed.app.run(host=application.bind_host, port=application.bind_port, threaded=True)
    finally:
        composed.close()


if __name__ == "__main__":
    main()
