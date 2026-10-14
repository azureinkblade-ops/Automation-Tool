"""The fake inspect transport cannot turn a matching report into launch authority."""

import hashlib
import json

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tools.hermes_core.agent_local_kilo_daemon_observer import (
    AgentLocalKiloDaemonObserver,
)
from tools.hermes_core.agent_local_kilo_docker_read_client import (
    AgentLocalKiloDockerReadClient,
)


def test_fake_transport_observer_matches_but_denies_start(tmp_path):
    start, values, spec, _, _, args = setup(tmp_path)
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"fake docker executable")
    calls = []
    reports = {
        "container": values["container"],
        "image": values["image"],
        "network": values["network"],
    }

    def runner(argv, *, timeout_seconds, max_output_bytes):
        calls.append((argv, timeout_seconds, max_output_bytes))
        return json.dumps([reports[argv[3]]]).encode("utf-8")

    client = AgentLocalKiloDockerReadClient(
        str(executable), hashlib.sha256(executable.read_bytes()).hexdigest(),
        runner=runner,
    )
    observer = AgentLocalKiloDaemonObserver(values["records"], read_client=client)
    try:
        result = observer.review(*args, gateway_id=values["gateway_id"])
        record = values["records"].get(values["attempt_id"])
        assert result.decision == "MATCH"
        assert result.reason == "CREATE_SPEC_REVIEW_ONLY_START_DENIED"
        assert result.receiver_executed is False
        assert result.provenance_checked is False
        assert [call[0][-1] for call in calls] == [
            record.container_id, spec["image_manifest"], record.network_id,
        ]
        assert all(call[1:] == (5, 1024 * 1024) for call in calls)
    finally:
        start.close()


def test_fake_transport_observer_rejects_wrong_image_id(tmp_path):
    start, values, _, _, _, args = setup(tmp_path)
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"fake docker executable")

    def runner(argv, *, timeout_seconds, max_output_bytes):
        kind = argv[3]
        report = dict(values[kind])
        if kind == "image":
            report["Id"] = "sha256:" + "0" * 64
        return json.dumps([report]).encode("utf-8")

    client = AgentLocalKiloDockerReadClient(
        str(executable), hashlib.sha256(executable.read_bytes()).hexdigest(),
        runner=runner,
    )
    observer = AgentLocalKiloDaemonObserver(values["records"], read_client=client)
    try:
        result = observer.review(*args, gateway_id=values["gateway_id"])
        assert result.decision == "DENY"
        assert result.reason == "DAEMON_READ_FAILED"
    finally:
        start.close()
