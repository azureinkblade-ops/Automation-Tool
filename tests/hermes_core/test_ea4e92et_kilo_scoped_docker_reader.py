"""Fake command runner only; no Docker daemon is contacted."""

import json

import pytest

from tools.hermes_core.kilo_scoped_docker_reader import (
    ScopedDockerReadDenied,
    ScopedDockerSnapshotReader,
)


NETWORK, RECEIVER, GATEWAY = "e" * 64, "f" * 64, "a" * 64


def test_reader_issues_only_three_exact_inspects():
    calls = []

    def fake(argv):
        calls.append(argv)
        return json.dumps([{"Id": argv[-1]}])

    snapshot = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER,
        gateway_id=GATEWAY, run_command=fake).read()
    assert calls == [
        ["docker", "network", "inspect", NETWORK],
        ["docker", "container", "inspect", RECEIVER],
        ["docker", "container", "inspect", GATEWAY],
    ]
    assert (snapshot.network["Id"], snapshot.receiver["Id"],
            snapshot.gateway["Id"]) == (NETWORK, RECEIVER, GATEWAY)


@pytest.mark.parametrize("identities", [
    ("wrong", RECEIVER, GATEWAY),
    (NETWORK, NETWORK, GATEWAY),
    (NETWORK, RECEIVER, "A" * 64),
])
def test_invalid_id_denied_before_runner(identities):
    with pytest.raises(ScopedDockerReadDenied, match="identities denied"):
        ScopedDockerSnapshotReader(
            network_id=identities[0], receiver_id=identities[1],
            gateway_id=identities[2],
            run_command=lambda _argv: pytest.fail("runner called"))


@pytest.mark.parametrize("raw", [
    "not JSON", "[]", "{}", json.dumps([{"Id": "0" * 64}]),
    json.dumps([{"Id": NETWORK}, {"Id": NETWORK}]),
])
def test_invalid_inspect_output_denied_before_next_read(raw):
    calls = []

    def fake(argv):
        calls.append(argv)
        return raw

    reader = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER,
        gateway_id=GATEWAY, run_command=fake)
    with pytest.raises(ScopedDockerReadDenied):
        reader.read()
    assert calls == [["docker", "network", "inspect", NETWORK]]


def test_oversized_inspect_output_denied():
    reader = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER,
        gateway_id=GATEWAY, run_command=lambda _argv: "x" * 262145)
    with pytest.raises(ScopedDockerReadDenied, match="output denied"):
        reader.read()


def test_default_command_failure_is_fail_closed(monkeypatch):
    class Failed:
        returncode = 1
        stdout = "private output"

    def fake_run(argv, **kwargs):
        assert argv == ["docker", "network", "inspect", NETWORK]
        assert kwargs["timeout"] == 10
        return Failed()

    monkeypatch.setattr("tools.hermes_core.kilo_scoped_docker_reader.subprocess.run",
                        fake_run)
    reader = ScopedDockerSnapshotReader(
        network_id=NETWORK, receiver_id=RECEIVER, gateway_id=GATEWAY)
    with pytest.raises(ScopedDockerReadDenied, match="Docker inspect failed"):
        reader.read()
