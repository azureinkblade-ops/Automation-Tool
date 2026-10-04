"""Fake-only preparation tests; Kilo and real providers are never launched."""

from __future__ import annotations

import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from threading import Thread

import pytest

from tools.ea4e92ck_kilo_inert_probe import (
    DUMMY_KEY, InertProviderHandler, MARKER, MODEL, MODEL_ID,
    fake_response, prepare,
)


def test_prepare_uses_fresh_home_and_never_authorizes_launch(tmp_path):
    binary = tmp_path / "fake-kilo.exe"
    binary.write_bytes(b"inert-binary-identity")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()

    output = prepare(tmp_path / "probe", 12345, binary=binary, expected_sha=digest)
    plan = json.loads(output.read_text(encoding="ascii"))
    assert plan["binary_sha256"] == digest
    assert plan["argv"][0] == str(binary.resolve())
    assert plan["argv"][plan["argv"].index("--model") + 1] == MODEL
    assert plan["launch_authorized"] is False
    assert plan["network_isolation_verified"] is False
    assert plan["real_provider_calls_authorized"] is False
    assert plan["credential_class"] == "DUMMY_LOCAL_ONLY"
    assert plan["env"]["HOME"].startswith(str(tmp_path / "probe"))
    assert plan["env"]["KILO_CONFIG_DIR"].startswith(str(tmp_path / "probe"))
    assert "kilo.db" not in json.dumps(plan).lower()
    assert json.loads((tmp_path / "probe/config/kilo.jsonc").read_text())["provider"][
        "openai-compatible"]["options"]["baseURL"] == "http://127.0.0.1:12345/v1"
    assert (tmp_path / "probe/home/.kilo/agents/hermes-ea4e-kilo-receiver/"
            "hermes-ea4e-kilo-receiver.jsonc").is_file()

    with pytest.raises(ValueError, match="probe root must be new"):
        prepare(tmp_path / "probe", 12345, binary=binary, expected_sha=digest)


def test_prepare_rejects_wrong_binary_hash_without_creating_root(tmp_path):
    binary = tmp_path / "fake-kilo.exe"
    binary.write_bytes(b"different")
    root = tmp_path / "probe"
    with pytest.raises(ValueError, match="hash mismatch"):
        prepare(root, 12345, binary=binary, expected_sha="0" * 64)
    assert not root.exists()


def test_fake_provider_responses_are_deterministic_and_never_forward():
    status, kind, body = fake_response("GET", "/v1/models", None)
    assert status == 200 and kind == "application/json"
    assert json.loads(body)["data"][0]["id"] == MODEL_ID

    status, kind, body = fake_response("POST", "/v1/chat/completions", {"model": MODEL_ID})
    assert status == 200 and kind == "application/json"
    assert json.loads(body)["choices"][0]["message"]["content"] == MARKER

    status, kind, body = fake_response(
        "POST", "/v1/chat/completions", {"model": MODEL_ID, "stream": True}
    )
    assert status == 200 and kind == "text/event-stream"
    assert b"data: [DONE]" in body

    assert fake_response("POST", "/v1/chat/completions", {"model": "real-model"})[0] == 400
    assert fake_response("POST", "/v1/responses", {"model": MODEL_ID})[0] == 404


@pytest.mark.skipif(
    os.environ.get("EA4E_RUN_LOOPBACK_FAKE_PROVIDER") != "1",
    reason="requires explicit loopback-only inert server test",
)
def test_loopback_handler_requires_dummy_key_and_does_not_accept_other_paths():
    with ThreadingHTTPServer(("127.0.0.1", 0), InertProviderHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            client.request("GET", "/v1/models")
            response = client.getresponse()
            assert response.status == 401
            response.read()

            client.request("GET", "/v1/models", headers={"Authorization": f"Bearer {DUMMY_KEY}"})
            response = client.getresponse()
            assert response.status == 200
            assert json.loads(response.read())["data"][0]["id"] == MODEL_ID

            client.request("POST", "/v1/responses", body=b"{}", headers={
                "Authorization": f"Bearer {DUMMY_KEY}", "Content-Type": "application/json",
            })
            response = client.getresponse()
            assert response.status == 404
            response.read()
            client.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
