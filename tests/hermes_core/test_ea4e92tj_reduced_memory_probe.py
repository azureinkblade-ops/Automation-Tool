"""Fake-only lower-memory probe tests; no Docker or model execution."""

from dataclasses import replace

import pytest

import tools.ea4e92tj_reduced_memory_probe as entry
from tools.ea4e92rm_container_smoke import SmokeDenied, SmokePlan, validate_plan
from tests.hermes_core.test_ea4e92rm_container_smoke import FakeDocker, plan_for, run_smoke


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
        assert plan.startup_log_diagnostic is True
        assert plan.mount_only_probe is True
        assert plan.reduced_memory_probe is True
        assert plan.memory_bytes == 8 * 1024**3
        calls.append(plan.name)
        return "EA4E_MOUNT_START_OK"

    monkeypatch.setattr(entry, "DockerCli", fake_client)
    monkeypatch.setattr(entry, "run_smoke", fake_smoke)
    assert entry.main() == "EA4E_MOUNT_START_OK"
    assert len(calls) == 1 and calls[0].startswith("ea4e92tj-")


def test_lower_memory_keeps_mount_and_no_http(tmp_path, monkeypatch):
    plan = replace(plan_for(tmp_path, monkeypatch), memory_bytes=8 * 1024**3,
                   startup_log_diagnostic=True, mount_only_probe=True,
                   reduced_memory_probe=True)
    docker = FakeDocker(plan)
    assert run_smoke(plan, docker, tags_only=True) == "EA4E_MOUNT_START_OK"
    created = next(args for args, _ in docker.calls if args[:2] == ("container", "create"))
    assert "--memory=8589934592" in created
    assert "--memory-swap=8589934592" in created
    assert "--network=none" in created
    assert "--read-only" in created
    assert "--mount" in created
    assert not any("/api/tags" in args or "/api/generate" in args
                   for args, _ in docker.calls)
    assert not docker.created


def test_lower_memory_failed_start_still_cleans_up(tmp_path, monkeypatch):
    plan = replace(plan_for(tmp_path, monkeypatch), memory_bytes=8 * 1024**3,
                   startup_log_diagnostic=True, mount_only_probe=True,
                   reduced_memory_probe=True)
    docker = FakeDocker(plan, fail_on="start-reject-cli")
    with pytest.raises(SmokeDenied, match="startup_category=permission_denied"):
        run_smoke(plan, docker, tags_only=True)
    assert not docker.created
    assert not any("/api/tags" in args or "/api/generate" in args
                   for args, _ in docker.calls)


def test_lower_memory_never_permitted_for_model_mode(tmp_path, monkeypatch):
    plan = replace(plan_for(tmp_path, monkeypatch), memory_bytes=8 * 1024**3,
                   reduced_memory_probe=True)
    with pytest.raises(SmokeDenied, match="unreviewed model or resource"):
        validate_plan(plan)


def test_arbitrary_memory_denied(tmp_path, monkeypatch):
    plan = replace(plan_for(tmp_path, monkeypatch), memory_bytes=7 * 1024**3,
                   startup_log_diagnostic=True, mount_only_probe=True,
                   reduced_memory_probe=True)
    with pytest.raises(SmokeDenied, match="unreviewed model or resource"):
        validate_plan(plan)


def test_non_boolean_mode_denied(tmp_path, monkeypatch):
    plan = replace(plan_for(tmp_path, monkeypatch), reduced_memory_probe=1)
    with pytest.raises(SmokeDenied, match="unreviewed model or resource"):
        validate_plan(plan)


def test_lower_memory_probe_cannot_infer(tmp_path, monkeypatch):
    plan = replace(plan_for(tmp_path, monkeypatch), memory_bytes=8 * 1024**3,
                   startup_log_diagnostic=True, mount_only_probe=True,
                   reduced_memory_probe=True)
    docker = FakeDocker(plan)
    with pytest.raises(SmokeDenied, match="requires tags-only mode"):
        run_smoke(plan, docker)
    assert not docker.calls
