"""Pure create-request proposal tests; no Docker command is run."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tools.hermes_core.agent_local_kilo_create_request import (
    build_provisional_kilo_create_request,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload


def _request(values, spec):
    return build_provisional_kilo_create_request(
        values["records"].intents, values["attempt_id"],
        values["v1_plan"], values["prepared"], spec,
    )


def test_create_request_is_deterministic_and_non_authorizing(tmp_path):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        request = _request(values, spec)
        assert request == _request(values, spec)
        assert request["create_authorized"] is False
        assert request["launch_authorized"] is False
        assert request["spec_hash"] == spec["spec_hash"]
        assert request["request_hash"] == sha256_payload({
            key: value for key, value in request.items() if key != "request_hash"
        })
        argv = request["argv"]
        assert argv[:4] == ["container", "create", "--name", spec["container_name"]]
        assert argv[-len(spec["argv"]) - 1] == spec["image_index"]
        assert argv[-len(spec["argv"]):] == spec["argv"]
        assert argv.count("--pull") == 1
        assert argv[argv.index("--pull") + 1] == "never"
        assert argv[argv.index("--network") + 1] == spec["network"]["name"]
        assert argv[argv.index("--cap-drop") + 1] == "ALL"
        assert argv[argv.index("--security-opt") + 1] == "no-new-privileges:true"
        assert argv[argv.index("--pids-limit") + 1] == "64"
        assert argv[argv.index("--memory") + 1] == str(2 * 1024 * 1024 * 1024)
        assert argv[argv.index("--cpus") + 1] == "2"
        assert argv[argv.index("--restart") + 1] == "no"
        assert argv[argv.index("--tmpfs") + 1].startswith("/work:rw,nosuid,nodev,noexec,")
        assert argv.count("--mount") == len(spec["mounts"])
        mounts = [argv[pos + 1] for pos, item in enumerate(argv) if item == "--mount"]
        assert sum(mount.endswith(",readonly") for mount in mounts) == 1
        assert sum(not mount.endswith(",readonly") for mount in mounts) == 1
        assert argv.count("--label") == len(spec["labels"])
        assert argv.count("--env") == len(spec["env"])
        assert "--read-only" in argv
        assert "--rm" not in argv
        assert "--publish" not in argv
        assert "--publish-all" not in argv
        assert "start" not in argv
    finally:
        start.close()


@pytest.mark.parametrize("field", [
    "container_name", "image_index", "host_policy", "mounts", "labels",
])
def test_changed_spec_denied(tmp_path, field):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        changed = deepcopy(spec)
        changed[field] = "changed"
        with pytest.raises(DelegationIntegrityError):
            _request(values, changed)
    finally:
        start.close()
