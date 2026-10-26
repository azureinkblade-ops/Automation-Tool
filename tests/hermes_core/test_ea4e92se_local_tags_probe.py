"""Fake-only tags diagnostic entrypoint tests; no Docker or model run."""

import tools.ea4e92se_local_tags_probe as entry


def test_fixed_tags_only_entrypoint(monkeypatch):
    calls = []
    client = object()

    def fake_client(binary, digest):
        assert binary == entry.DOCKER
        assert digest == entry.DOCKER_SHA256
        return client

    def fake_smoke(plan, observed_client, *, tags_only):
        assert observed_client is client
        assert tags_only is True
        assert plan.image == entry.IMAGE
        assert plan.image_id == entry.IMAGE_ID
        assert plan.models_root == entry.MODELS_ROOT
        calls.append(plan.ceremony_id)
        return "EA4E_LOCAL_TAGS_OK"

    monkeypatch.setattr(entry, "DockerCli", fake_client)
    monkeypatch.setattr(entry, "run_smoke", fake_smoke)
    assert entry.main() == "EA4E_LOCAL_TAGS_OK"
    assert len(calls) == 1
