"""Versioned pending-event lineage checks; no Docker or receiver activity."""

import ast
import inspect
import json

import pytest

from tools.hermes_core import kilo_ping_pending_event as subject


ATTEMPT = "attempt-1"
RESPONSE = "a" * 64
BODY = "b" * 64


def line(**changes):
    payload = {
        "event": "FAKE_PING_REQUEST_PENDING",
        "attempt_id": ATTEMPT,
        "response_sha256": RESPONSE,
        "peer": "172.20.0.2",
        "body_bytes": 123,
        "body_sha256": BODY,
    }
    payload.update(changes)
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("ascii")


def test_exact_event_is_lineage_bound_but_not_authority():
    parsed = subject.parse_ping_pending_event(
        line(), attempt_id=ATTEMPT, response_sha256=RESPONSE,
    )
    assert parsed == subject.PingPendingEvent(
        ATTEMPT, RESPONSE, "172.20.0.2", 123, BODY,
    )
    assert not hasattr(parsed, "release_authorized")
    assert not hasattr(parsed, "peer_qualified")


@pytest.mark.parametrize("raw", [
    line(event="FAKE_REQUEST_PENDING"),
    line(attempt_id="attempt-2"),
    line(response_sha256="c" * 64),
    line(peer="::ffff:172.20.0.2"),
    line(peer="0172.20.0.2"),
    line(body_bytes=0), line(body_bytes=True),
    line(body_sha256="B" * 64), line(extra="x"),
    line() + line(), line().rstrip(b"\n"),
    b'{"event":"FAKE_PING_REQUEST_PENDING","attempt_id":"attempt-1",'
    b'"attempt_id":"attempt-1","response_sha256":"' + RESPONSE.encode() +
    b'","peer":"172.20.0.2","body_bytes":1,"body_sha256":"' +
    BODY.encode() + b'"}\n',
    b"x" * 513 + b"\n",
])
def test_malformed_or_divergent_event_denied(raw):
    with pytest.raises(subject.PingPendingEventDenied):
        subject.parse_ping_pending_event(
            raw, attempt_id=ATTEMPT, response_sha256=RESPONSE,
        )


def test_expected_binding_cannot_be_malformed():
    with pytest.raises(subject.PingPendingEventDenied):
        subject.parse_ping_pending_event(
            line(), attempt_id="bad attempt", response_sha256=RESPONSE,
        )


def test_parser_has_no_runtime_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"subprocess", "socket", "requests", "os"})
