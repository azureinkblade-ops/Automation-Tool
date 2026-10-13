"""Synthetic attempt-bound ping through the existing fake-only gateway."""

import hashlib
import json

import pytest

from tests.hermes_core.test_ea4e92ib_local_kilo_ping_intent import accepted
from tools.ea4e92bw_fake_streaming_qualification import FakeSseResponse
from tools.ea4e92dw_kilo_dynamic_fake_gateway import (
    DynamicFakeDenied,
    DynamicFakeScope,
    KiloDynamicFakeGateway,
    provision_dynamic_fake_budget,
)
from tools.hermes_core.agent_local_kilo_fake_ping_body import (
    build_agent_local_kilo_fake_ping_body,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)


TOKEN = "Bearer synthetic-child-only"
NOW = "2026-10-06T00:00:01Z"
PEER = ("e" * 64, "f" * 64)
REQUEST = json.dumps({
    "model": "ea4e-inert",
    "messages": [
        {"role": "system", "content": "dummy policy"},
        {"role": "user", "content": ["synthetic ping"]},
    ],
    "stream": True,
    "stream_options": {},
    "tools": [],
    "tool_choice": "auto",
    "max_tokens": 64,
}, sort_keys=True, separators=(",", ":")).encode("ascii")


def test_attempt_bound_sse_passes_one_use_fake_gateway(tmp_path):
    _, start, task, lease, bridges, _ = accepted(tmp_path)
    try:
        witness = load_bound_agent_start(bridges.authority, start, lease.attempt_id)
        response = build_agent_local_kilo_fake_ping_body(
            witness, bridges.get(lease.attempt_id),
        )
        scope = DynamicFakeScope(
            run_id="synthetic-ping", source_commit="a" * 40,
            transport_id="b" * 64, model_binding_id="c" * 64,
            task_hash=task.task_input_hash, network_id=PEER[0],
            container_id=PEER[1],
            token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
            issued_at="2026-10-06T00:00:00Z",
            expires_at="2026-10-06T00:05:00Z",
        )
        store = DurableInvocationAuthorizationStore.initialize(
            tmp_path / "fake-gateway.sqlite3",
            anchor_path=tmp_path / "fake-gateway-anchor.json",
        )
        provision_dynamic_fake_budget(store, scope)
        replies = []

        def respond(_body):
            replies.append(1)
            return FakeSseResponse(200, "text/event-stream", None,
                                   ((response["sse_bytes"], 0),))

        gateway = KiloDynamicFakeGateway(
            store, scope, verify_peer=lambda expected, observed: observed == PEER,
            respond=respond,
        )
        request = dict(
            run_id=scope.run_id, task_hash=scope.task_hash,
            connection_context=PEER, method="POST",
            path="/v1/chat/completions", content_type="application/json",
            authorization=TOKEN, body=REQUEST, now=NOW,
        )
        with pytest.raises(DynamicFakeDenied):
            gateway.request(**(request | {"task_hash": "0" * 64}))
        assert replies == []
        assert store.consumed_count() == 0

        result = gateway.request(**request)
        assert result.response_bytes == response["sse_bytes"]
        assert hashlib.sha256(result.response_bytes).hexdigest() == response["sse_sha256"]
        event = json.loads(result.response_bytes.split(b"\n\n", 1)[0][6:])
        assert event["choices"][0]["delta"]["content"] == response["candidate_json"]
        assert len(replies) == 1
        assert store.consumed_count() == 1
        with pytest.raises(DynamicFakeDenied):
            gateway.request(**request)
        assert len(replies) == 1
    finally:
        start.close()
