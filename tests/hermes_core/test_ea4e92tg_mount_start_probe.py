"""Fake-only mount/start entrypoint test; no Docker or model execution."""

import tools.ea4e92tg_mount_start_probe as entry


def test_mount_start_entrypoint_is_non_model(monkeypatch):
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
        assert plan.image == entry.IMAGE
        assert plan.image_id == entry.IMAGE_ID
        assert plan.models_root == entry.MODELS_ROOT
        calls.append(plan.ceremony_id)
        return "EA4E_MOUNT_START_OK"

    monkeypatch.setattr(entry, "DockerCli", fake_client)
    monkeypatch.setattr(entry, "run_smoke", fake_smoke)
    assert entry.main() == "EA4E_MOUNT_START_OK"
    assert len(calls) == 1
