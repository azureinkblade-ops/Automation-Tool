"""One-shot non-model Bash loopback capability probe; exact approval required."""

import json

from tools.ea4e92rq_nonmodel_probe import run


if __name__ == "__main__":
    print(json.dumps(run(mode="bash"), sort_keys=True))
