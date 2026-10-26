"""One-shot tags-only startup diagnostic; exact native authorization required."""

import json
from uuid import uuid4

from tools.ea4e92rm_container_smoke import DockerCli, SmokePlan, run_smoke
from tools.ea4e92sb_local_model_smoke import (
    DOCKER, DOCKER_SHA256, IMAGE, IMAGE_ID, MODELS_ROOT,
)


def main() -> str:
    plan = SmokePlan(IMAGE, IMAGE_ID, MODELS_ROOT, str(uuid4()),
                     startup_log_diagnostic=True)
    return run_smoke(plan, DockerCli(DOCKER, DOCKER_SHA256), tags_only=True)


if __name__ == "__main__":
    print(json.dumps({"marker": main()}, sort_keys=True))
