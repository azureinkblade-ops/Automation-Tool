"""Fake-only GPU-hidden probe tests; no Docker or model execution."""

from dataclasses import replace

import pytest

import tools.ea4e92tq_gpu_hidden_probe as entry
from tools.ea4e92rm_container_smoke import SmokeDenied, validate_plan
from tests.hermes_core.test_ea4e92rm_container_smoke import FakeDocker, plan_for, run_smoke


def hidden_plan(tmp_path, monkeypatch):
    return replace(plan_for(tmp_path, monkeypatch), memory_bytes=8 * 1024**3,
                   startup_log_diagnostic=True, mount_only_probe=True,
                   reduced_memory_probe=True, no_mount_probe=True,
                   gpu_hidden_probe=True)


def test_entrypoint_is_non_model(monkeypatch):
    client = object()
    calls = []

    def fake_client(binary, digest, *, classify_start_failure):
        assert binary == entry.DOCKER
        assert digest == entry.DOCKER_SHA256
        assert classify_start_failure is True
        return client

    def fake_smoke(plan, observed_client, *, tags_only):
        assert observed_client is client and tags_only is True
        assert plan.gpu_hidden_probe and plan.no_mount_probe
        assert plan.memory_bytes == 8 * 1024**3
        calls.append(plan.name)
        return "EA4E_MOUNT_START_OK"

    monkeypatch.setattr(entry, "DockerCli", fake_client)
    monkeypatch.setattr(entry, "run_smoke", fake_smoke)
    assert entry.main() == "EA4E_MOUNT_START_OK"
    assert len(calls) == 1 and calls[0].startswith("ea4e92tq-")


def test_gpu_hidden_no_mount_and_no_http(tmp_path, monkeypatch):
    plan = hidden_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan)
    assert run_smoke(plan, docker, tags_only=True) == "EA4E_MOUNT_START_OK"
    created = next(args for args, _ in docker.calls if args[:2] == ("container", "create"))
    assert created.count("NVIDIA_VISIBLE_DEVICES=void") == 1
    assert "--gpus" not in created and "--mount" not in created
    assert "--network=none" in created
    assert not any("/api/tags" in args or "/api/generate" in args
                   for args, _ in docker.calls)
    assert not docker.created


def test_gpu_hidden_failed_start_still_cleans_up(tmp_path, monkeypatch):
    plan = hidden_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="start-reject-cli")
    with pytest.raises(SmokeDenied, match="startup_category=permission_denied"):
        run_smoke(plan, docker, tags_only=True)
    assert not docker.created


@pytest.mark.parametrize("failure", ["gpu-visible", "gpu-hidden-missing"])
def test_gpu_hidden_requires_effective_void(tmp_path, monkeypatch, failure):
    plan = hidden_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on=failure)
    with pytest.raises(SmokeDenied, match="gpu_hidden"):
        run_smoke(plan, docker, tags_only=True)
    assert not docker.started
    assert not docker.created


def test_gpu_hidden_requires_no_mount(tmp_path, monkeypatch):
    plan = replace(hidden_plan(tmp_path, monkeypatch), no_mount_probe=False)
    with pytest.raises(SmokeDenied, match="unreviewed model or resource"):
        validate_plan(plan)


def test_gpu_hidden_cannot_infer(tmp_path, monkeypatch):
    plan = hidden_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan)
    with pytest.raises(SmokeDenied, match="requires tags-only mode"):
        run_smoke(plan, docker)
    assert not docker.calls
