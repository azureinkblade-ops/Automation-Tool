"""Single synthetic local-model smoke entrypoint; exact authorization required."""

import json
from pathlib import Path
from uuid import uuid4

from tools.ea4e92rm_container_smoke import DockerCli, SmokePlan, run_smoke


IMAGE = "ollama/ollama@sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da"
IMAGE_ID = "sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da"
DOCKER = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
DOCKER_SHA256 = "c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c"
MODELS_ROOT = Path(
    r"C:\Users\David\Documents\Automation tool\.worktrees\ea4e67-kilo762-roll"
    r"\output\ea4e92rs-model-stage-11befaa388f0474f9d3b3d50ab63f364"
)


def main() -> str:
    plan = SmokePlan(IMAGE, IMAGE_ID, MODELS_ROOT, str(uuid4()))
    client = DockerCli(DOCKER, DOCKER_SHA256)
    return run_smoke(plan, client)


if __name__ == "__main__":
    print(json.dumps({"marker": main()}, sort_keys=True))
