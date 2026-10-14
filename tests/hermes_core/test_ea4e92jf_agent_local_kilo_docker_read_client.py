"""Fake Docker CLI runner only; no daemon is contacted."""

import hashlib
import json

import pytest

from tools.hermes_core.agent_local_kilo_docker_read_client import (
    AgentLocalKiloDockerReadClient,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


CONTAINER_ID = "a" * 64
NETWORK_ID = "b" * 64
IMAGE_ID = "sha256:" + "c" * 64
IMAGE_INDEX = "sha256:" + "d" * 64


def fixture(tmp_path, *, response=None):
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"inert fake executable")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    calls = []

    def runner(argv, *, timeout_seconds, max_output_bytes):
        calls.append((argv, timeout_seconds, max_output_bytes))
        if response is not None:
            return response
        return json.dumps([{"Id": IMAGE_ID if "image" in argv else argv[-1]}]).encode("utf-8")

    client = AgentLocalKiloDockerReadClient(
        str(executable), digest, runner=runner,
    )
    return executable, digest, client, calls


def test_exact_read_commands_and_bounds(tmp_path):
    executable, _, client, calls = fixture(tmp_path)
    assert client.inspect_container(CONTAINER_ID)["Id"] == CONTAINER_ID
    assert client.inspect_image(IMAGE_INDEX, IMAGE_ID)["Id"] == IMAGE_ID
    assert client.inspect_network(NETWORK_ID)["Id"] == NETWORK_ID
    assert calls == [
        ((str(executable), "--context", "desktop-linux", "container",
          "inspect", CONTAINER_ID), 5, 1024 * 1024),
        ((str(executable), "--context", "desktop-linux", "image",
          "inspect", "--platform", "linux/amd64", IMAGE_INDEX), 5, 1024 * 1024),
        ((str(executable), "--context", "desktop-linux", "network",
          "inspect", NETWORK_ID), 5, 1024 * 1024),
    ]
    assert all("start" not in argv and "create" not in argv
               for argv, _, _ in calls)


def test_default_disabled_and_changed_executable_deny(tmp_path):
    executable, digest, client, calls = fixture(tmp_path)
    disabled = AgentLocalKiloDockerReadClient(str(executable), digest)
    with pytest.raises(DelegationIntegrityError, match="disabled"):
        disabled.inspect_container(CONTAINER_ID)
    executable.write_bytes(b"changed")
    with pytest.raises(DelegationIntegrityError, match="executable changed"):
        client.inspect_container(CONTAINER_ID)
    assert calls == []


@pytest.mark.parametrize("kind,identity", [
    ("container", "bad"),
    ("container", IMAGE_ID),
    ("network", "bad"),
    ("image", CONTAINER_ID),
    ("image", "sha256:" + "g" * 64),
])
def test_invalid_identity_denied_before_runner(tmp_path, kind, identity):
    _, _, client, calls = fixture(tmp_path)
    with pytest.raises(DelegationIntegrityError, match="identity denied"):
        if kind == "image":
            client.inspect_image(identity, IMAGE_ID)
        else:
            getattr(client, f"inspect_{kind}")(identity)
    assert calls == []


def test_invalid_manifest_denied_before_runner(tmp_path):
    _, _, client, calls = fixture(tmp_path)
    with pytest.raises(DelegationIntegrityError, match="manifest identity denied"):
        client.inspect_image(IMAGE_INDEX, "bad")
    assert calls == []


def test_wrong_platform_manifest_denied(tmp_path):
    _, _, client, _ = fixture(
        tmp_path, response=json.dumps([{"Id": IMAGE_INDEX}]).encode("utf-8"),
    )
    with pytest.raises(DelegationIntegrityError, match="image mismatch"):
        client.inspect_image(IMAGE_INDEX, IMAGE_ID)


@pytest.mark.parametrize("response,reason", [
    (b"", "output bounds"),
    ("oversize", "output bounds"),
    (b"\xff", "JSON denied"),
    (b'[{"Id":"a","Id":"b"}]', "JSON denied"),
    (b'[{"Id":NaN}]', "JSON denied"),
    (b"[]", "response shape"),
    (b'[{"Id":"other"}]', "object mismatch"),
])
def test_bad_output_denied(tmp_path, response, reason):
    if response == "oversize":
        response = b"x" * (1024 * 1024 + 1)
    _, _, client, _ = fixture(tmp_path, response=response)
    with pytest.raises(DelegationIntegrityError, match=reason):
        client.inspect_container(CONTAINER_ID)
