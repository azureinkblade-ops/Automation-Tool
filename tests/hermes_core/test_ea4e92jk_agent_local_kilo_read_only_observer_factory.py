"""Composed fake process/observer tests; no Docker daemon is contacted."""

import hashlib
import json

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tests.hermes_core.test_ea4e92jj_agent_local_kilo_bounded_inspect_runner import (
    FakeProcess,
)
from tools.hermes_core.agent_local_kilo_read_only_observer_factory import (
    build_local_kilo_read_only_observer,
)


def test_composed_read_only_observer_never_grants_start(tmp_path):
    start, values, spec, _, _, args = setup(tmp_path)
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"fake executable")
    config = tmp_path / "empty-config"
    config.mkdir()
    calls = []
    reports = {
        "container": values["container"],
        "image": values["image"],
        "network": values["network"],
    }

    def spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        return FakeProcess(stdout=json.dumps([reports[argv[3]]]).encode("utf-8"))

    observer = build_local_kilo_read_only_observer(
        values["records"], str(executable),
        hashlib.sha256(executable.read_bytes()).hexdigest(), str(config),
        popen_factory=spawn,
    )
    try:
        result = observer.review(*args, gateway_id=values["gateway_id"])
        record = values["records"].get(values["attempt_id"])
        assert result.decision == "MATCH"
        assert result.reason == "CREATE_SPEC_REVIEW_ONLY_START_DENIED"
        assert result.receiver_executed is False
        assert result.provenance_checked is False
        assert [call[0][-1] for call in calls] == [
            record.container_id, spec["image_index"], record.network_id,
        ]
        assert all(call[1]["shell"] is False for call in calls)
        assert all(call[1]["env"]["DOCKER_CONFIG"] == str(config)
                   for call in calls)
    finally:
        start.close()


def test_composed_observer_denies_changed_image_metadata(tmp_path):
    start, values, _, _, _, args = setup(tmp_path)
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"fake executable")
    config = tmp_path / "empty-config"
    config.mkdir()
    reports = {
        "container": values["container"],
        "image": {**values["image"], "Id": "sha256:" + "0" * 64},
        "network": values["network"],
    }

    def spawn(argv, **_kwargs):
        return FakeProcess(stdout=json.dumps([reports[argv[3]]]).encode("utf-8"))

    observer = build_local_kilo_read_only_observer(
        values["records"], str(executable),
        hashlib.sha256(executable.read_bytes()).hexdigest(), str(config),
        popen_factory=spawn,
    )
    try:
        result = observer.review(*args, gateway_id=values["gateway_id"])
        assert result.decision == "DENY"
        assert result.reason == "DAEMON_READ_FAILED"
    finally:
        start.close()
