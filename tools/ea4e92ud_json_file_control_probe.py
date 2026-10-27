"""One-shot non-model json-file logging comparison; exact approval required."""

import json

from tools.ea4e92rq_nonmodel_probe import run


if __name__ == "__main__":
    print(json.dumps(run(mode="bash", json_file_log=True), sort_keys=True))
