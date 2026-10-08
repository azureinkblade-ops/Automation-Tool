"""Inert executable file and fake command runner; no Docker daemon contact."""

import hashlib
import json

import pytest

from tools.hermes_core.kilo_scoped_docker_reader import (
    ScopedDockerReadDenied,
    ScopedDockerSnapshotReader,
)


NETWORK, RECEIVER, GATEWAY = "e" * 64, "f" * 64, "a" * 64


@pytest.fixture
def docker_pin(tmp_path):
    path = tmp_path / "inert-docker.exe"
    path.write_bytes(b"fake executable identity only")
    return {"docker_executable": str(path),
            "docker_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_reader_issues_only_three_exact_inspects(docker_pin):
    calls = []

    def fake(argv):
        calls.append(argv)
        return json.dumps([{"Id": argv[-1]}])

    snapshot = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER,
        gateway_id=GATEWAY, run_command=fake, **docker_pin).read()
    assert calls == [
        [docker_pin["docker_executable"], "network", "inspect", NETWORK],
        [docker_pin["docker_executable"], "container", "inspect", RECEIVER],
        [docker_pin["docker_executable"], "container", "inspect", GATEWAY],
    ]
    assert (snapshot.network["Id"], snapshot.receiver["Id"],
            snapshot.gateway["Id"]) == (NETWORK, RECEIVER, GATEWAY)


@pytest.mark.parametrize("identities", [
    ("wrong", RECEIVER, GATEWAY),
    (NETWORK, NETWORK, GATEWAY),
    (NETWORK, RECEIVER, "A" * 64),
])
def test_invalid_id_denied_before_runner(identities, docker_pin):
    with pytest.raises(ScopedDockerReadDenied, match="identities denied"):
        ScopedDockerSnapshotReader(
            network_id=identities[0], receiver_id=identities[1],
            gateway_id=identities[2],
            run_command=lambda _argv: pytest.fail("runner called"), **docker_pin)


@pytest.mark.parametrize("raw", [
    "not JSON", "[]", "{}", json.dumps([{"Id": "0" * 64}]),
    json.dumps([{"Id": NETWORK}, {"Id": NETWORK}]),
])
def test_invalid_inspect_output_denied_before_next_read(raw, docker_pin):
    calls = []

    def fake(argv):
        calls.append(argv)
        return raw

    reader = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER,
        gateway_id=GATEWAY, run_command=fake, **docker_pin)
    with pytest.raises(ScopedDockerReadDenied):
        reader.read()
    assert calls == [[docker_pin["docker_executable"], "network", "inspect", NETWORK]]


def test_oversized_inspect_output_denied(docker_pin):
    reader = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER,
        gateway_id=GATEWAY, run_command=lambda _argv: "x" * 262145,
        **docker_pin)
    with pytest.raises(ScopedDockerReadDenied, match="output denied"):
        reader.read()


def test_default_command_failure_is_fail_closed(monkeypatch, docker_pin):
    class Failed:
        returncode = 1
        stdout = "private output"

    def fake_run(argv, **kwargs):
        assert argv == [docker_pin["docker_executable"], "network", "inspect", NETWORK]
        assert kwargs["timeout"] == 10
        return Failed()

    monkeypatch.setattr("tools.hermes_core.kilo_scoped_docker_reader.subprocess.run",
                        fake_run)
    reader = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER, gateway_id=GATEWAY,
        **docker_pin)
    with pytest.raises(ScopedDockerReadDenied, match="Docker inspect failed"):
        reader.read()


def test_executable_drift_denied_before_command(docker_pin):
    calls = []
    reader = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER, gateway_id=GATEWAY,
        run_command=lambda argv: calls.append(argv), **docker_pin)
    with open(docker_pin["docker_executable"], "ab") as target:
        target.write(b"drift")
    with pytest.raises(ScopedDockerReadDenied, match="hash denied"):
        reader.read()
    assert calls == []
