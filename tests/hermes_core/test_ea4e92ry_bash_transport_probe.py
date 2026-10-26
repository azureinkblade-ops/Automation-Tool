"""Fake-only tests for the one-shot non-model transport probe."""

import json

import pytest

import tools.ea4e92rq_nonmodel_probe as probe
from tools.ea4e92rm_container_smoke import SmokeDenied


CONTAINER_ID = "c" * 64


class FakeDocker:
    def __init__(self, *, shell_result="Connection refused"):
        self.shell_result = shell_result
        self.name = None
        self.label = None
        self.created = False
        self.running = False
        self.calls = []

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
            self.name = args[args.index("--name") + 1]
            self.label = args[args.index("--label") + 1]
            self.created = True
            return (CONTAINER_ID + "\n").encode()
        if args[:2] == ("container", "inspect"):
            assert self.created
            return json.dumps([{
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
                    "LogConfig": {"Type": "none"},
                    "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=16777216"},
                    "PortBindings": None,
                },
                "NetworkSettings": {"Ports": None, "Networks": {"none": {}}},
                "Mounts": [], "State": {"Running": self.running},
            }]).encode()
        if args[:2] == ("container", "start"):
            self.running = True
            return CONTAINER_ID.encode()
        if args[:2] == ("container", "exec"):
            assert self.running and args[2:5] == (CONTAINER_ID, "/bin/sh", "-c")
            assert args[5] == probe.BASH_CHECK
            return ("tool:/bin/bash:yes\n" + self.shell_result + "\n"
                    "tool:/bin/cat:yes\nnet:lo: 0 0 0 0\n").encode()
        if args[:2] == ("container", "rm"):
            assert args[2:] == ("--force", CONTAINER_ID)
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
