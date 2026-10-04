"""Privacy-bounded shape capture tests; no Kilo or real provider."""

import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from threading import Lock, Thread

import pytest

from tools.ea4e92ck_kilo_inert_probe import DUMMY_KEY, InertProviderHandler, MODEL_ID
from tools.ea4e92cp_kilo_request_shape import (
    RequestShapeDenied, summarize_request_shape,
)


SECRET = "PRIVATE_SENTINEL_DO_NOT_RECORD"
BODY = json.dumps({
    "model": MODEL_ID, "stream": True,
    "messages": [{"role": "user", "content": SECRET, SECRET: "hidden"}],
    SECRET: "hidden",
}).encode("utf-8")


def test_summary_contains_only_allowlisted_shape():
    shape = summarize_request_shape(BODY, expected_model=MODEL_ID)
    assert shape["body_bytes"] == len(BODY)
    assert shape["body_sha256"] == hashlib.sha256(BODY).hexdigest()
    assert shape["field_types"] == {
        "model": "string", "messages": "array", "stream": "boolean",
    }
    assert shape["unknown_field_count"] == 1
    assert shape["message_unknown_field_count"] == 1
    assert shape["role_counts"]["user"] == 1
    assert shape["content_kind_counts"]["string"] == 1
    assert shape["stream_true"] is True
    assert SECRET not in json.dumps(shape)


@pytest.mark.parametrize("raw", [
    b"", b"x" * 65537, b"not json",
    b'{"model":"ea4e-inert","messages":[],"stream":true,"stream":true}',
    b'{"model":"ea4e-inert","messages":[],"x":NaN}',
    b'{"model":"other","messages":[]}',
    b'{"model":"ea4e-inert","messages":{}}',
    b'{"model":"ea4e-inert","messages":["secret"]}',
], ids=["empty", "oversize", "not-json", "duplicate-key", "nonfinite",
        "wrong-model", "messages-object", "message-string"])
def test_invalid_body_denied_without_echo(raw):
    with pytest.raises(RequestShapeDenied) as error:
        summarize_request_shape(raw, expected_model=MODEL_ID)
    assert SECRET not in str(error.value)


@pytest.mark.skipif(os.environ.get("EA4E_RUN_LOOPBACK_FAKE_PROVIDER") != "1",
                    reason="requires explicit loopback-only fake server test")
def test_loopback_event_records_shape_without_content_or_header(capsys):
    class RecordingServer(ThreadingHTTPServer):
        def __init__(self, address):
            super().__init__(address, InertProviderHandler)
            self.events = []
            self.event_lock = Lock()

    with RecordingServer(("127.0.0.1", 0)) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            client.request("POST", "/v1/chat/completions", body=BODY, headers={
                "Authorization": f"Bearer {DUMMY_KEY}", "Content-Type": "application/json",
            })
            response = client.getresponse()
            assert response.status == 200
            response.read()
            client.request("POST", "/" + SECRET, body=json.dumps({
                "model": MODEL_ID, "messages": [], "stream": SECRET,
            }), headers={"Authorization": f"Bearer {DUMMY_KEY}"})
            response = client.getresponse()
            assert response.status == 404
            response.read()
            client.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
    assert len(server.events) == 2
    assert server.events[0]["request_shape"] == summarize_request_shape(
        BODY, expected_model=MODEL_ID)
    assert server.events[1]["path"] == "<other>"
    assert server.events[1]["stream"] is False
    recorded = json.dumps(server.events) + capsys.readouterr().out
    assert SECRET not in recorded
    assert DUMMY_KEY not in recorded
