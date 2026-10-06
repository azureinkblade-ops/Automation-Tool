"""Synthetic-only Kilo shape tests. No gateway, receiver, or provider."""

import ast
import hashlib
import inspect
import json

import pytest

from tools.hermes_core import kilo_inert_request_shape as subject


def body(content="synthetic only", **changes):
    payload = {
        "model": "ea4e-inert",
        "messages": [
            {"role": "system", "content": "dummy policy"},
            {"role": "user", "content": [content]},
        ],
        "stream": True,
        "stream_options": {},
        "tools": [],
        "tool_choice": "auto",
        "max_tokens": 64,
    }
    payload.update(changes)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")


def test_observed_synthetic_shape_matches_without_forward_authority():
    raw = body()
    result = subject.inspect_inert_kilo_request(raw)
    assert result == {
        "decision": "SHAPE_MATCH_ONLY",
        "body_bytes": len(raw),
        "body_sha256": hashlib.sha256(raw).hexdigest(),
        "forward_authorized": False,
    }


def test_different_prompt_bytes_match_same_shape_but_not_same_identity():
    first = subject.inspect_inert_kilo_request(body("first dummy prompt"))
    second = subject.inspect_inert_kilo_request(body("second dummy prompt"))
    assert first["decision"] == second["decision"] == "SHAPE_MATCH_ONLY"
    assert first["body_sha256"] != second["body_sha256"]
    assert not first["forward_authorized"] and not second["forward_authorized"]


def test_synthetic_body_at_observed_size_is_shape_only():
    raw = body("x" * (64878 - len(body(""))))
    assert len(raw) == 64878
    assert subject.inspect_inert_kilo_request(raw)["forward_authorized"] is False


@pytest.mark.parametrize("raw", [
    body(model="other"),
    body(stream=False),
    body(extra="unexpected"),
    body(tools="not an array"),
    body(messages=[{"role": "user", "content": "only one"}]),
    body(messages=[{"role": "system", "content": "x"},
                   {"role": "user", "content": "wrong kind"}]),
    b'{"model":"ea4e-inert","model":"ea4e-inert"}',
    b"x" * 65537,
], ids=["wrong-model", "not-streaming", "unknown-field", "tools-type",
        "one-message", "content-kind", "duplicate-key", "oversize"])
def test_non_observed_or_unsafe_shapes_denied(raw):
    with pytest.raises(subject.InertRequestDenied, match="dummy request shape denied"):
        subject.inspect_inert_kilo_request(raw)


def test_no_runtime_or_content_capture_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"subprocess", "requests", "socket"})
