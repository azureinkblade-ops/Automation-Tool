"""One-shot lower-memory non-model mount probe; exact authorization required."""

import json
from uuid import uuid4

from tools.ea4e92rm_container_smoke import DockerCli, SmokePlan, run_smoke
from tools.ea4e92sb_local_model_smoke import (
    DOCKER, DOCKER_SHA256, IMAGE, IMAGE_ID, MODELS_ROOT,
)


def main() -> str:
    plan = SmokePlan(IMAGE, IMAGE_ID, MODELS_ROOT, str(uuid4()),
                     memory_bytes=8 * 1024**3, startup_log_diagnostic=True,
                     mount_only_probe=True, reduced_memory_probe=True)
    return run_smoke(
        plan, DockerCli(DOCKER, DOCKER_SHA256, classify_start_failure=True),
        tags_only=True)


if __name__ == "__main__":
    print(json.dumps({"marker": main()}, sort_keys=True))
