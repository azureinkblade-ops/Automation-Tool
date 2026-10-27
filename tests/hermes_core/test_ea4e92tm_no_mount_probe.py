"""Fake-only no-mount probe tests; no Docker or model execution."""

from dataclasses import replace

import pytest

import tools.ea4e92tm_no_mount_probe as entry
from tools.ea4e92rm_container_smoke import SmokeDenied, validate_plan
from tests.hermes_core.test_ea4e92rm_container_smoke import FakeDocker, plan_for, run_smoke


def no_mount_plan(tmp_path, monkeypatch):
    return replace(plan_for(tmp_path, monkeypatch), memory_bytes=8 * 1024**3,
                   startup_log_diagnostic=True, mount_only_probe=True,
                   reduced_memory_probe=True, no_mount_probe=True)


def test_entrypoint_is_one_shot_non_model(monkeypatch):
    calls = []
    client = object()

    def fake_client(binary, digest, *, classify_start_failure):
        assert binary == entry.DOCKER
        assert digest == entry.DOCKER_SHA256
        assert classify_start_failure is True
        return client

    def fake_smoke(plan, observed_client, *, tags_only):
        assert observed_client is client
        assert tags_only is True
        assert plan.no_mount_probe is True
        assert plan.reduced_memory_probe is True
        assert plan.mount_only_probe is True
        calls.append(plan.name)
        return "EA4E_MOUNT_START_OK"

    monkeypatch.setattr(entry, "DockerCli", fake_client)
    monkeypatch.setattr(entry, "run_smoke", fake_smoke)
    assert entry.main() == "EA4E_MOUNT_START_OK"
    assert len(calls) == 1 and calls[0].startswith("ea4e92tm-")


def test_no_mount_preserves_containment_and_skips_http(tmp_path, monkeypatch):
    plan = no_mount_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan)
    assert run_smoke(plan, docker, tags_only=True) == "EA4E_MOUNT_START_OK"
    created = next(args for args, _ in docker.calls if args[:2] == ("container", "create"))
    assert "--mount" not in created
    assert "--network=none" in created
    assert "--read-only" in created
    assert "--memory=8589934592" in created
    assert "--memory-swap=8589934592" in created
    assert not any("/api/tags" in args or "/api/generate" in args
                   for args, _ in docker.calls)
    assert not docker.created


def test_no_mount_failed_start_still_cleans_up(tmp_path, monkeypatch):
    plan = no_mount_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="start-reject-cli")
    with pytest.raises(SmokeDenied, match="startup_category=permission_denied"):
        run_smoke(plan, docker, tags_only=True)
    assert not docker.created


def test_no_mount_rejects_unexpected_mount(tmp_path, monkeypatch):
    plan = no_mount_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan, fail_on="unexpected-mount")
    with pytest.raises(SmokeDenied, match="mount_count"):
        run_smoke(plan, docker, tags_only=True)
    assert not docker.started
    assert not docker.created


def test_no_mount_denied_without_reduced_memory(tmp_path, monkeypatch):
    plan = replace(no_mount_plan(tmp_path, monkeypatch),
                   reduced_memory_probe=False, memory_bytes=20 * 1024**3)
    with pytest.raises(SmokeDenied, match="unreviewed model or resource"):
        validate_plan(plan)


def test_no_mount_non_boolean_flag_denied(tmp_path, monkeypatch):
    plan = replace(no_mount_plan(tmp_path, monkeypatch), no_mount_probe=1)
    with pytest.raises(SmokeDenied, match="unreviewed model or resource"):
        validate_plan(plan)


def test_no_mount_cannot_infer(tmp_path, monkeypatch):
    plan = no_mount_plan(tmp_path, monkeypatch)
    docker = FakeDocker(plan)
    with pytest.raises(SmokeDenied, match="requires tags-only mode"):
        run_smoke(plan, docker)
    assert not docker.calls
