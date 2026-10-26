"""Fake-only contract tests; no Docker daemon or model is invoked."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
import tools.ea4e92rm_container_smoke as smoke

from tools.ea4e92rm_container_smoke import (
    SmokeDenied, SmokePlan, UnknownContainerOutcome, run_smoke, validate_plan,
)


IMAGE = "ollama/ollama@sha256:" + "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
CONTAINER_ID = "c" * 64


def plan_for(tmp_path: Path, monkeypatch) -> SmokePlan:
    models = tmp_path / "models"
    files = []
    for index in range(6):
        name = ("manifests/registry.ollama.ai/library/qwen3/14b" if index == 0
                else f"blobs/sha256-synthetic-{index}")
        model = models / name
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(f"synthetic model identity {index}".encode())
        files.append((name, hashlib.sha256(model.read_bytes()).hexdigest()))
    monkeypatch.setattr(smoke, "EXPECTED_MODEL_FILES", tuple(files))
    return SmokePlan(
        IMAGE, IMAGE_ID, models, str(uuid4()),
    )


class FakeDocker:
    def __init__(self, plan, *, interfaces="lo", fail_on=None):
        self.plan = plan
        self.interfaces = interfaces
        self.fail_on = fail_on
        self.calls = []
        self.created = False
        self.running = False
        self.owner_token = None

    def _inspection(self):
        return [{
            "Id": CONTAINER_ID, "Name": "/" + self.plan.name,
            "Image": IMAGE_ID,
            "Config": {"Image": IMAGE, "Cmd": ["serve"],
                       "Entrypoint": ["/bin/ollama"], "ExposedPorts": None,
                       "Labels": {"ea4e92rm.owner": self.owner_token},
                       "Env": ["HOME=/tmp", "OLLAMA_MODELS=/models",
                               "OLLAMA_HOST=127.0.0.1:11434", "OLLAMA_KEEP_ALIVE=0"]},
            "HostConfig": {
                "NetworkMode": "none", "ReadonlyRootfs": True,
                "Privileged": False, "Memory": self.plan.memory_bytes,
                "MemorySwap": self.plan.memory_bytes,
                "PidsLimit": 64, "NanoCpus": 4_000_000_000,
                "CapDrop": ["ALL"], "CapAdd": None,
                "Devices": [], "DeviceRequests": [],
                "SecurityOpt": ["no-new-privileges"],
                "RestartPolicy": {"Name": "no"}, "PortBindings": None,
                "LogConfig": {"Type": "none"},
                "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=2147483648"},
            },
            "Mounts": [{"Type": "bind", "Source": str(self.plan.models_root),
                        "Destination": "/models", "RW": False}],
            "NetworkSettings": {"Ports": None, "Networks": {"none": {}}},
            "State": {"Running": self.running},
        }]

    def invoke(self, args, *, timeout, stdin=b"", output_limit=1024 * 1024):
        self.calls.append((args, stdin))
        assert 0 < timeout <= 120
        if args[:2] == ("image", "inspect"):
            return json.dumps([{"Id": IMAGE_ID, "RepoDigests": [IMAGE]}]).encode()
        if args[:2] == ("container", "create"):
            assert not self.created
            assert "--network=none" in args
            assert "--read-only" in args
            assert "--cap-drop=ALL" in args
            assert "--pull=never" in args
            assert "--restart=no" in args
            assert "--gpus" not in args
            assert "--publish" not in args
            self.owner_token = args[args.index("--label") + 1].split("=", 1)[1]
            self.created = True
            if self.fail_on == "collision":
                self.owner_token = "different-owner"
                raise SmokeDenied("name collision")
            if self.fail_on == "create":
                raise SmokeDenied("fake create failure")
            return (CONTAINER_ID + "\n").encode()
        if args[:2] == ("container", "inspect"):
            assert self.created and args[2] in (CONTAINER_ID, self.plan.name)
            observation = self._inspection()
            if self.fail_on == "network":
                observation[0]["HostConfig"]["NetworkMode"] = "bridge"
            if self.fail_on == "cpu":
                observation[0]["HostConfig"]["NanoCpus"] = 0
            if self.fail_on == "owner":
                observation[0]["Config"]["Labels"]["ea4e92rm.owner"] = "other"
            return json.dumps(observation).encode()
        if args[:2] == ("container", "start"):
            assert self.created and not self.running
            self.running = True
            return CONTAINER_ID.encode()
        if args[:2] == ("container", "kill"):
            assert args[2] == CONTAINER_ID
            if not self.running:
                raise SmokeDenied("not running")
            self.running = False
            return CONTAINER_ID.encode()
        if args[:2] == ("container", "rm"):
            assert args[2] == CONTAINER_ID and self.created and not self.running
            if self.fail_on == "remove":
                raise SmokeDenied("fake removal failure")
            self.created = False
            return CONTAINER_ID.encode()
        if args[:2] == ("container", "ls"):
            assert args[-1] == f"id={CONTAINER_ID}"
            return b"" if not self.created else (CONTAINER_ID + "\n").encode()
        if args[:2] == ("container", "exec"):
            assert self.running
            if "/proc/net/dev" in args:
                lines = "Inter-| Receive\n face | bytes\n"
                lines += "lo: 0 0 0 0\n"
                if self.interfaces != "lo":
                    lines += "eth0: 0 0 0 0\n"
                return lines.encode()
            assert args[3:9] == (
                "/bin/ollama", "run", "--format=json", "--think=false",
                "--keepalive=0", "--nowordwrap")
            assert args[9] == "qwen3:14b"
            assert args[10] == ("Reply only as JSON with exactly one key, marker, "
                                "whose value is EA4E_LOCAL_SMOKE_OK.")
            assert not stdin
            if self.fail_on == "model-drift":
                (self.plan.models_root / "blobs" / "sha256-synthetic-1").write_bytes(b"changed")
            marker = ("not the requested marker" if self.fail_on == "wrong-answer"
                      else "EA4E_LOCAL_SMOKE_OK")
            answer = {"marker": marker}
            if self.fail_on == "duplicate-key":
                return b'{"marker":"wrong","marker":"EA4E_LOCAL_SMOKE_OK"}'
            if self.fail_on == "extra-field":
                answer["extra"] = "unexpected"
            return json.dumps(answer).encode()
        raise AssertionError(args)


def test_one_synthetic_request_and_owned_stop(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan)
    assert run_smoke(plan, docker) == "EA4E_LOCAL_SMOKE_OK"
    assert not docker.running
    requests = [args for args, _ in docker.calls if args[:2] == ("container", "exec")
                and "/bin/ollama" in args]
    assert len(requests) == 1
    assert ("container", "kill", CONTAINER_ID) in [args for args, _ in docker.calls]
    assert docker.calls[-2][0] == ("container", "rm", CONTAINER_ID)
    assert not docker.created


@pytest.mark.parametrize("failure", ["network", "interfaces", "cpu"])
def test_denial_still_stops_exact_container(tmp_path, monkeypatch, failure):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan, interfaces="eth0" if failure == "interfaces" else "lo",
                        fail_on=failure if failure in ("network", "cpu") else None)
    with pytest.raises(SmokeDenied):
        run_smoke(plan, docker)
    assert not docker.running
    assert not any(args[:2] == ("container", "exec") and "/bin/ollama" in args
                   for args, _ in docker.calls)


def test_model_file_drift_denied_before_docker(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    (plan.models_root / "blobs" / "sha256-synthetic-1").write_bytes(b"changed")
    with pytest.raises(SmokeDenied, match="model file identity"):
        run_smoke(plan, FakeDocker(plan))


def test_unrelated_model_file_denied_before_docker(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    (plan.models_root / "blobs" / "unrelated").write_bytes(b"private")
    with pytest.raises(SmokeDenied, match="unrelated files"):
        run_smoke(plan, FakeDocker(plan))


def test_model_drift_during_request_denies_and_stops(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="model-drift")
    with pytest.raises(SmokeDenied, match="model file identity"):
        run_smoke(plan, docker)
    assert not docker.running


@pytest.mark.parametrize("failure", ["wrong-answer", "extra-field", "duplicate-key"])
def test_wrong_model_answer_denies_and_stops(tmp_path, monkeypatch, failure):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on=failure)
    with pytest.raises(SmokeDenied, match="response contract"):
        run_smoke(plan, docker)
    assert not docker.running
    assert not docker.created


def test_unreadable_model_directory_denied_before_docker(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)

    def failed_walk(root, *, followlinks, onerror):
        onerror(OSError("unreadable directory"))
        return iter(())

    monkeypatch.setattr(smoke.os, "walk", failed_walk)
    with pytest.raises(SmokeDenied, match="inventory traversal"):
        run_smoke(plan, FakeDocker(plan))


def test_unpinned_image_denied(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    invalid = SmokePlan("ollama/ollama:latest", plan.image_id, plan.models_root,
                        plan.ceremony_id)
    with pytest.raises(SmokeDenied, match="digest-pinned"):
        validate_plan(invalid)


def test_create_failure_is_unknown(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="create")
    with pytest.raises(UnknownContainerOutcome):
        run_smoke(plan, docker)
    assert not docker.running


def test_name_collision_never_kills_other_container(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="collision")
    with pytest.raises(UnknownContainerOutcome):
        run_smoke(plan, docker)
    assert not any(args[:2] == ("container", "kill") for args, _ in docker.calls)


def test_failed_removal_is_not_reported_as_success(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="remove")
    with pytest.raises(UnknownContainerOutcome, match="cleanup requires reconciliation"):
        run_smoke(plan, docker)
    assert not docker.running
    assert docker.created


def test_unverified_returned_id_never_kills_container(tmp_path, monkeypatch):
    plan = plan_for(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="owner")
    with pytest.raises(UnknownContainerOutcome):
        run_smoke(plan, docker)
    assert not any(args[:2] == ("container", "kill") for args, _ in docker.calls)
