"""Fake-only entrypoint test; never starts Docker or a model."""

import tools.ea4e92sb_local_model_smoke as entry


def test_fixed_single_synthetic_entrypoint(monkeypatch):
    calls = []
    client = object()

    def fake_client(binary, digest):
        assert binary == entry.DOCKER
        assert digest == entry.DOCKER_SHA256
        return client

    def fake_smoke(plan, observed_client):
        assert observed_client is client
        assert plan.image == entry.IMAGE
        assert plan.image_id == entry.IMAGE_ID
        assert plan.models_root == entry.MODELS_ROOT
        assert plan.model == "qwen3:14b"
        calls.append(plan.ceremony_id)
        return "EA4E_LOCAL_SMOKE_OK"

    monkeypatch.setattr(entry, "DockerCli", fake_client)
    monkeypatch.setattr(entry, "run_smoke", fake_smoke)
    assert entry.main() == "EA4E_LOCAL_SMOKE_OK"
    assert len(calls) == 1
