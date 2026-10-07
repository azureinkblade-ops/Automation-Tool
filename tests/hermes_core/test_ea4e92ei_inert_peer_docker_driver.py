"""Mocked command surface only; never invokes Docker."""

import pytest

from tools.hermes_core import inert_peer_probe_docker as subject


def test_exact_acknowledgement_required_before_driver_creation(monkeypatch):
    monkeypatch.setattr(subject, "DockerProbeDriver",
                        lambda: pytest.fail("driver created"))
    for argv in ([], ["--approved-once"], ["--approved-once", "wrong"]):
        with pytest.raises(ValueError):
            subject.main(argv)


def test_owned_ids_and_one_gateway_signal_only(monkeypatch):
    calls = []
    outputs = iter(["network-id\n", "gateway-id\n", "client-id\n",
                    "gateway-id\n", "client-id\n", "gateway-id\n", "network-id\n"])

    def fake_call(argv, timeout=10):
        calls.append(argv)
        return next(outputs)

    monkeypatch.setattr(subject.DockerProbeDriver, "_call", staticmethod(fake_call))
    driver = subject.DockerProbeDriver()
    assert driver.create_network(["docker", "network", "create", "example"]) == "network-id"
    assert driver.create_container(["docker", "container", "create", "gateway"]) == "gateway-id"
    assert driver.create_container(["docker", "container", "create", "client"]) == "client-id"
    with pytest.raises(ValueError):
        driver.signal_gateway("client-id", "SIGUSR2")
    driver.signal_gateway("gateway-id", "SIGUSR2")
    with pytest.raises(ValueError):
        driver.signal_gateway("gateway-id", "SIGUSR2")
    driver.remove_container("client-id")
    driver.remove_container("gateway-id")
    driver.remove_network("network-id")
    assert calls[-4:] == [
        ["docker", "kill", "--signal=SIGUSR2", "gateway-id"],
        ["docker", "container", "rm", "--force", "client-id"],
        ["docker", "container", "rm", "--force", "gateway-id"],
        ["docker", "network", "rm", "network-id"],
    ]
    assert not driver.owned_containers and not driver.owned_networks


def test_unowned_mutations_denied(monkeypatch):
    monkeypatch.setattr(subject.DockerProbeDriver, "_call",
                        staticmethod(lambda argv, timeout=10: pytest.fail("Docker called")))
    driver = subject.DockerProbeDriver()
    for action in (driver.start_container, driver.remove_container,
                   driver.remove_network):
        with pytest.raises(ValueError):
            action("other-id")
    with pytest.raises(ValueError):
        driver.signal_gateway("other-id", "SIGUSR2")


def test_subprocess_never_uses_shell(monkeypatch):
    seen = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs))
        return Result()

    monkeypatch.setattr(subject.subprocess, "run", fake_run)
    assert subject.DockerProbeDriver._call(["docker", "version"]) == "ok"
    assert seen[0][0] == ["docker", "version"]
    assert "shell" not in seen[0][1] or seen[0][1]["shell"] is False
    with pytest.raises(ValueError):
        subject.DockerProbeDriver._call(["powershell", "-Command", "anything"])
