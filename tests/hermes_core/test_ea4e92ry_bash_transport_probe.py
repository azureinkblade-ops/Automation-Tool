"""Fake-only tests for the one-shot non-model transport probe."""

import json

import pytest

import tools.ea4e92rq_nonmodel_probe as probe
from tools.ea4e92rm_container_smoke import SmokeDenied


CONTAINER_ID = "c" * 64


class FakeDocker:
    def __init__(self, *, shell_result="Connection refused", fail_on=None):
        self.shell_result = shell_result
        self.fail_on = fail_on
        self.name = None
        self.label = None
        self.created = False
        self.running = False
        self.calls = []
        self.local_log = False

    def invoke(self, args, *, timeout, stdin=b"", output_limit=1024 * 1024):
        self.calls.append(args)
        assert 0 < timeout <= 10
        if args[:2] == ("image", "inspect"):
            return json.dumps([{
                "Id": probe.IMAGE_ID, "RepoDigests": [probe.IMAGE],
                "Os": "linux", "Architecture": "amd64",
            }]).encode()
        if args[:2] == ("container", "create"):
            assert "--network=none" in args and "--pull=never" in args
            assert "--read-only" in args and "--cap-drop=ALL" in args
            assert "--gpus" not in args and "--publish" not in args
            assert "--mount" not in args
            self.local_log = "--log-driver=local" in args
            if self.local_log:
                assert "--log-driver=none" not in args
                assert args.count("--log-opt") == 2
                assert "max-size=16k" in args and "max-file=1" in args
            else:
                assert "--log-driver=none" in args
            self.name = args[args.index("--name") + 1]
            self.label = args[args.index("--label") + 1]
            self.created = True
            if self.fail_on in ("create", "collision"):
                raise SmokeDenied("fake create outcome")
            return (CONTAINER_ID + "\n").encode()
        if args[:2] == ("container", "inspect"):
            assert self.created
            observed = {
                "Id": CONTAINER_ID, "Name": "/" + self.name,
                "Image": probe.IMAGE_ID,
                "Config": {
                    "Labels": dict([self.label.split("=", 1)]),
                    "Image": probe.IMAGE, "Entrypoint": ["/bin/sh"],
                    "Cmd": ["-c", "sleep 45"],
                    "Env": ["NVIDIA_VISIBLE_DEVICES=void"],
                },
                "HostConfig": {
                    "NetworkMode": "none", "ReadonlyRootfs": True,
                    "Privileged": False, "Memory": probe.MEMORY,
                    "MemorySwap": probe.MEMORY, "PidsLimit": 16,
                    "NanoCpus": 1_000_000_000, "CapDrop": ["ALL"],
                    "CapAdd": None, "Devices": [], "DeviceRequests": [],
                    "SecurityOpt": ["no-new-privileges"],
                    "RestartPolicy": {"Name": "no"},
                    "LogConfig": ({"Type": "local", "Config": {
                        "max-size": "16k", "max-file": "1"}}
                                  if self.local_log else {"Type": "none"}),
                    "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=16777216"},
                    "PortBindings": None,
                },
                "NetworkSettings": {"Ports": None, "Networks": {"none": {}}},
                "Mounts": [], "State": {"Running": self.running},
            }
            if self.fail_on == "network":
                observed["HostConfig"]["NetworkMode"] = "bridge"
            if self.fail_on == "logging":
                observed["HostConfig"]["LogConfig"] = {"Type": "none"}
            if self.fail_on == "collision":
                observed["Config"]["Labels"][self.label.split("=", 1)[0]] = "other"
            return json.dumps([observed]).encode()
        if args[:2] == ("container", "start"):
            if self.fail_on == "start":
                raise SmokeDenied("fixed start denial")
            self.running = True
            return CONTAINER_ID.encode()
        if args[:2] == ("container", "exec"):
            assert self.running and args[2:5] == (CONTAINER_ID, "/bin/sh", "-c")
            assert args[5] == probe.BASH_CHECK
            return ("tool:/bin/bash:yes\n" + self.shell_result + "\n"
                    "tool:/bin/cat:yes\nnet:lo: 0 0 0 0\n").encode()
        if args[:2] == ("container", "rm"):
            assert args[2:] == ("--force", CONTAINER_ID)
            if self.fail_on == "remove":
                raise SmokeDenied("fake remove failure")
            self.created = self.running = False
            return CONTAINER_ID.encode()
        if args[:2] == ("container", "ls"):
            return b"" if not self.created else (CONTAINER_ID + "\n").encode()
        raise AssertionError(args)


def test_one_bash_probe_and_exact_cleanup(monkeypatch):
    docker = FakeDocker()
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    result = probe.run(mode="bash")
    assert result["interfaces"] == ["lo"]
    assert result["tools"] == ["tool:/bin/bash:yes", "tool:/bin/cat:yes"]
    assert not docker.created
    assert sum(args[:2] == ("container", "exec") for args in docker.calls) == 1


def test_local_log_only_variant_keeps_control_and_exact_cleanup(monkeypatch):
    docker = FakeDocker()
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    result = probe.run(mode="bash", local_log=True)
    assert result["interfaces"] == ["lo"]
    assert docker.local_log
    assert docker.name.startswith("ea4e92tz-")
    assert not docker.created
    assert sum(args[:2] == ("container", "start") for args in docker.calls) == 1


def test_local_log_mismatch_denied_before_start_and_cleaned(monkeypatch):
    docker = FakeDocker(fail_on="logging")
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    with pytest.raises(SmokeDenied, match="prestart restrictions"):
        probe.run(mode="bash", local_log=True)
    assert not any(args[:2] == ("container", "start") for args in docker.calls)
    assert not docker.created


def test_local_log_start_failure_is_one_attempt_and_cleaned(monkeypatch):
    docker = FakeDocker(fail_on="start")
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    with pytest.raises(SmokeDenied, match="fixed start denial"):
        probe.run(mode="bash", local_log=True)
    assert sum(args[:2] == ("container", "start") for args in docker.calls) == 1
    assert not docker.created


@pytest.mark.parametrize("mode,local_log", [("tools", True), ("bash", 1)])
def test_local_log_unreviewed_mode_denied_before_docker(monkeypatch, mode, local_log):
    monkeypatch.setattr(probe, "DockerCli", lambda *_: pytest.fail("Docker reached"))
    with pytest.raises(SmokeDenied, match="unreviewed"):
        probe.run(mode=mode, local_log=local_log)


def test_missing_bash_tcp_denied_and_cleaned(monkeypatch):
    docker = FakeDocker(shell_result="No such file or directory")
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    with pytest.raises(SmokeDenied, match="transport unproven"):
        probe.run(mode="bash")
    assert not docker.created


def test_unreviewed_mode_denied_before_docker(monkeypatch):
    monkeypatch.setattr(probe, "DockerCli", lambda *_: pytest.fail("Docker reached"))
    with pytest.raises(SmokeDenied, match="unreviewed"):
        probe.run(mode="model")


def test_restriction_mismatch_denied_before_start_and_cleaned(monkeypatch):
    docker = FakeDocker(fail_on="network")
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    with pytest.raises(SmokeDenied, match="prestart restrictions"):
        probe.run(mode="bash")
    assert not any(args[:2] == ("container", "start") for args in docker.calls)
    assert not docker.created


def test_name_collision_never_removes_unowned_container(monkeypatch):
    docker = FakeDocker(fail_on="collision")
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    with pytest.raises(SmokeDenied, match="cleanup unconfirmed"):
        probe.run(mode="bash")
    assert not any(args[:2] == ("container", "rm") for args in docker.calls)


def test_uncertain_create_is_reconciled_by_owner(monkeypatch):
    docker = FakeDocker(fail_on="create")
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    with pytest.raises(SmokeDenied, match="fake create outcome"):
        probe.run(mode="bash")
    assert not docker.created


def test_failed_removal_is_not_a_pass(monkeypatch):
    docker = FakeDocker(fail_on="remove")
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    with pytest.raises(SmokeDenied, match="cleanup unconfirmed"):
        probe.run(mode="bash")
    assert docker.created


def test_expired_deadline_denied_before_docker_call(monkeypatch):
    docker = FakeDocker()
    ticks = iter([0.0, 96.0])
    monkeypatch.setattr(probe, "DockerCli", lambda *_: docker)
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(ticks))
    with pytest.raises(SmokeDenied, match="deadline"):
        probe.run(mode="bash")
    assert not docker.calls
