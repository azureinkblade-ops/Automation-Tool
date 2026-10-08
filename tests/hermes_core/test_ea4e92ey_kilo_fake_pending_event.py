"""Source-only fake gateway event tests; no Docker or receiver calls."""

import ast
import inspect
import json

import pytest

from tools.hermes_core import kilo_fake_pending_event as subject


HASH = "a" * 64


def event(**changes):
    payload = {"event": "FAKE_REQUEST_PENDING", "peer": "172.20.0.2",
               "body_bytes": 64878, "body_sha256": HASH}
    payload.update(changes)
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("ascii")


def test_exact_event_is_shape_only():
    parsed = subject.parse_fake_pending_event(event())
    assert parsed == subject.FakePendingEvent("172.20.0.2", 64878, HASH)
    assert not hasattr(parsed, "peer_qualified")
    assert not hasattr(parsed, "send_authorized")


@pytest.mark.parametrize("raw", [
    event(event="OTHER"), event(peer="172.20.0.3\nforged"),
    event(peer="::ffff:172.20.0.2"), event(peer="0172.20.0.2"),
    event(body_bytes=0), event(body_bytes=65537), event(body_bytes=True),
    event(body_sha256="A" * 64), event(body_sha256="a" * 63),
    event(extra="x"), event() + event(), event().rstrip(b"\n"),
    b'{"event":"FAKE_REQUEST_PENDING","peer":"172.20.0.2",'
    b'"body_bytes":1,"body_bytes":1,"body_sha256":"' + HASH.encode() + b'"}\n',
    b"x" * 513 + b"\n",
], ids=["wrong-event", "injected-peer", "mapped-ipv6", "noncanonical-ip",
        "empty", "oversize", "boolean-size", "uppercase-hash", "short-hash",
        "extra-field", "two-lines", "missing-newline", "duplicate-field",
        "oversize-line"])
def test_malformed_or_unbound_event_denied(raw):
    with pytest.raises(subject.FakePendingEventDenied):
        subject.parse_fake_pending_event(raw)


def test_no_runtime_capabilities():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"subprocess", "socket", "requests", "os"})
