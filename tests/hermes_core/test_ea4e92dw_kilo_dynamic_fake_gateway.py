"""One-send dynamic-body fixture tests; no listener, receiver, or provider."""

from concurrent.futures import ThreadPoolExecutor
import ast
import hashlib
import inspect
import json

import pytest

from tools.ea4e92bw_fake_streaming_qualification import FakeSseResponse
from tools.ea4e92dw_kilo_dynamic_fake_gateway import (
    DynamicFakeDenied,
    DynamicFakeScope,
    KiloDynamicFakeGateway,
    provision_dynamic_fake_budget,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableAuthorizationStoreError,
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.kilo_fake_peer_binding import (
    SyntheticAcceptedPeer,
    SyntheticDockerSnapshot,
    make_fake_peer_verifier,
)
from tools.hermes_core import kilo_fake_peer_binding
from tools.hermes_core.kilo_fake_raw_peer import (
    FakeRawPeerBinding,
    FakeRawPeerSnapshot,
    make_fake_raw_peer_verifier,
)
from tools.hermes_core.opencode_sse_response import SseResponseDenied


TOKEN = "Bearer dummy-child-only"
NOW = "2026-10-06T00:00:01Z"
SSE = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
PEER = ("e" * 64, "f" * 64)


def body(content="synthetic only"):
    return json.dumps({
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
    }, sort_keys=True, separators=(",", ":")).encode("ascii")


def fixture(root, *, respond=None, verify_peer=None):
    scope = DynamicFakeScope(
        run_id="dynamic-fake-run", source_commit="a" * 40,
        transport_id="b" * 64, model_binding_id="c" * 64,
        task_hash="d" * 64, network_id=PEER[0], container_id=PEER[1],
        token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
        issued_at="2026-10-06T00:00:00Z", expires_at="2026-10-06T00:05:00Z",
    )
    store = DurableInvocationAuthorizationStore.initialize(
        root / "dynamic-budget.sqlite3", anchor_path=root / "anchor.json")
    provision_dynamic_fake_budget(store, scope)
    if verify_peer is None:
        verify_peer = lambda expected, observed: observed == (
            expected.network_id, expected.container_id)
    if respond is None:
        respond = lambda _body: FakeSseResponse(200, "text/event-stream", None,
                                                ((SSE, 0),))
    return KiloDynamicFakeGateway(store, scope, verify_peer=verify_peer,
                                  respond=respond)


def request(gate, **changes):
    values = dict(run_id=gate.scope.run_id, task_hash=gate.scope.task_hash,
                  connection_context=PEER, method="POST",
                  path="/v1/chat/completions", content_type="application/json",
                  authorization=TOKEN, body=body(), now=NOW)
    values.update(changes)
    return gate.request(**values)


def synthetic_snapshot(*, receiver_ip="172.20.0.2", extra_member=False):
    members = {PEER[1]: receiver_ip, "a" * 64: "172.20.0.3"}
    if extra_member:
        members["b" * 64] = "172.20.0.4"
    return SyntheticDockerSnapshot(
        network={"id": PEER[0], "driver": "bridge", "internal": True,
                 "members": members},
        receiver={"id": PEER[1], "running": True,
                  "network_ids": [PEER[0]], "published_ports": []},
        gateway={"id": "a" * 64, "running": True,
                 "network_ids": [PEER[0]], "published_ports": []},
    )


def test_synthetic_peer_snapshot_is_rechecked_inside_claim(tmp_path):
    reads = []

    def read_snapshot():
        reads.append(1)
        return synthetic_snapshot()

    verifier = make_fake_peer_verifier(gateway_id="a" * 64,
                                       read_snapshot=read_snapshot)
    gate = fixture(tmp_path, verify_peer=verifier)
    result = request(gate, connection_context=SyntheticAcceptedPeer("172.20.0.2"))
    assert result.response_bytes == SSE
    assert len(reads) == 2
    assert gate.store.consumed_count() == 1


def test_synthetic_peer_drift_before_claim_denies_without_consuming(tmp_path):
    reads = []

    def read_snapshot():
        reads.append(1)
        return synthetic_snapshot(extra_member=len(reads) == 2)

    verifier = make_fake_peer_verifier(gateway_id="a" * 64,
                                       read_snapshot=read_snapshot)
    gate = fixture(tmp_path, verify_peer=verifier)
    with pytest.raises(DurableAuthorizationStoreError, match="peer binding denied"):
        request(gate, connection_context=SyntheticAcceptedPeer("172.20.0.2"))
    assert len(reads) == 2
    assert gate.store.consumed_count() == 0


@pytest.mark.parametrize("context", [
    SyntheticAcceptedPeer("172.20.0.3"),
    (PEER[0], PEER[1]),
])
def test_synthetic_host_or_untyped_peer_denied(tmp_path, context):
    verifier = make_fake_peer_verifier(gateway_id="a" * 64,
                                       read_snapshot=synthetic_snapshot)
    gate = fixture(tmp_path, verify_peer=verifier)
    with pytest.raises(DynamicFakeDenied, match="peer binding denied"):
        request(gate, connection_context=context)
    assert gate.store.consumed_count() == 0


def test_synthetic_snapshot_missing_denies_without_claim(tmp_path):
    verifier = make_fake_peer_verifier(gateway_id="a" * 64,
                                       read_snapshot=lambda: None)
    gate = fixture(tmp_path, verify_peer=verifier)
    with pytest.raises(DynamicFakeDenied, match="peer binding denied"):
        request(gate, connection_context=SyntheticAcceptedPeer("172.20.0.2"))
    assert gate.store.consumed_count() == 0


def test_synthetic_peer_binding_has_no_runtime_imports():
    tree = ast.parse(inspect.getsource(kilo_fake_peer_binding))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports == {"dataclasses", "tools.hermes_core.docker_peer_candidate"}


def raw_snapshot(*, extra_member=False):
    network_name = "ea4e-fake-attempt"
    network = {"Id": PEER[0], "Name": network_name, "Driver": "bridge",
               "Internal": True, "EnableIPv6": False,
               "Containers": {
                   PEER[1]: {"IPv4Address": "172.20.0.2/16"},
                   "a" * 64: {"IPv4Address": "172.20.0.3/16"},
               }}
    if extra_member:
        network["Containers"]["b" * 64] = {"IPv4Address": "172.20.0.4/16"}

    def container(identity, ip):
        return {"Id": identity, "State": {"Running": True},
                "HostConfig": {"NetworkMode": network_name,
                               "PublishAllPorts": False, "PortBindings": {}},
                "NetworkSettings": {
                    "Networks": {network_name: {"NetworkID": PEER[0],
                                               "IPAddress": ip}},
                    "Ports": {"3080/tcp": None},
                }}

    return FakeRawPeerSnapshot(network, container(PEER[1], "172.20.0.2"),
                               container("a" * 64, "172.20.0.3"))


def test_raw_peer_records_are_rechecked_at_fake_claim(tmp_path):
    reads = []

    def read_records():
        reads.append(1)
        return raw_snapshot()

    verifier = make_fake_raw_peer_verifier(
        binding=FakeRawPeerBinding("ea4e-fake-attempt", "a" * 64),
        read_records=read_records)
    gate = fixture(tmp_path, verify_peer=verifier)
    assert request(gate, connection_context=SyntheticAcceptedPeer("172.20.0.2")).response_bytes == SSE
    assert len(reads) == 2
    assert gate.store.consumed_count() == 1


def test_raw_peer_drift_before_claim_denies_without_consuming(tmp_path):
    reads = []

    def read_records():
        reads.append(1)
        return raw_snapshot(extra_member=len(reads) == 2)

    verifier = make_fake_raw_peer_verifier(
        binding=FakeRawPeerBinding("ea4e-fake-attempt", "a" * 64),
        read_records=read_records)
    gate = fixture(tmp_path, verify_peer=verifier)
    with pytest.raises(DurableAuthorizationStoreError, match="peer binding denied"):
        request(gate, connection_context=SyntheticAcceptedPeer("172.20.0.2"))
    assert len(reads) == 2
    assert gate.store.consumed_count() == 0


def test_dynamic_body_claims_once_and_replay_after_restart_is_denied(tmp_path):
    calls = []
    gate = fixture(tmp_path, respond=lambda raw: calls.append(raw) or
                   FakeSseResponse(200, "text/event-stream", None, ((SSE, 0),)))
    first = body("first dummy")
    result = request(gate, body=first)
    assert result.response_bytes == SSE
    assert result.body_sha256 == hashlib.sha256(first).hexdigest()
    assert result.body_bytes == len(first)
    assert gate.store.consumed_count() == 1
    reopened = DurableInvocationAuthorizationStore(
        gate.store.path, anchor_path=gate.store.anchor_path)
    retry = KiloDynamicFakeGateway(reopened, gate.scope,
                                   verify_peer=gate.verify_peer, respond=gate.respond)
    with pytest.raises(DynamicFakeDenied, match="budget consumed"):
        request(retry, body=body("different dummy"))
    assert calls == [first]


@pytest.mark.parametrize("change", [
    {"connection_context": ("0" * 64, PEER[1])},
    {"task_hash": "0" * 64},
    {"run_id": "other"},
    {"authorization": "Bearer wrong"},
    {"method": "GET"},
    {"path": "/v1/models"},
    {"content_type": "text/plain"},
    {"body": b'{"model":"other"}'},
    {"now": "2026-10-06T00:05:00Z"},
    {"cancelled": True},
    {"revoked": True},
], ids=["wrong-peer", "wrong-task", "wrong-run", "wrong-token",
        "wrong-method", "wrong-route", "wrong-content-type", "bad-body",
        "expired", "cancelled", "revoked"])
def test_wrong_identity_or_body_does_not_claim_or_call_fake(tmp_path, change):
    calls = []
    gate = fixture(tmp_path, respond=lambda raw: calls.append(raw))
    with pytest.raises(DynamicFakeDenied):
        request(gate, **change)
    assert gate.store.consumed_count() == 0
    assert calls == []


def test_token_holder_without_independent_peer_match_is_denied(tmp_path):
    gate = fixture(tmp_path, verify_peer=lambda _scope, _context: False)
    with pytest.raises(DynamicFakeDenied, match="peer binding denied"):
        request(gate)
    assert gate.store.consumed_count() == 0


def test_concurrent_dynamic_requests_reach_fake_callback_once(tmp_path):
    calls = []
    gate = fixture(tmp_path, respond=lambda raw: calls.append(raw) or
                   FakeSseResponse(200, "text/event-stream", None, ((SSE, 0),)))

    def attempt(index):
        try:
            return request(gate, body=body(f"dummy {index}")).response_bytes
        except DynamicFakeDenied:
            return b"denied"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count(SSE) == 1
    assert results.count(b"denied") == 3
    assert gate.store.consumed_count() == len(calls) == 1


def test_fake_timeout_consumes_budget_without_retry(tmp_path):
    calls = []

    def timeout(raw):
        calls.append(raw)
        raise TimeoutError("synthetic timeout")

    gate = fixture(tmp_path, respond=timeout)
    with pytest.raises(TimeoutError):
        request(gate)
    with pytest.raises(DynamicFakeDenied):
        request(gate)
    assert gate.store.consumed_count() == len(calls) == 1


def test_precommit_failure_never_calls_fake(tmp_path, monkeypatch):
    calls = []
    gate = fixture(tmp_path, respond=lambda raw: calls.append(raw))

    def fail(_connection):
        raise RuntimeError("synthetic precommit failure")

    monkeypatch.setattr(gate.store, "_before_claim_commit", fail)
    with pytest.raises(DurableAuthorizationStoreError):
        request(gate)
    assert gate.store.consumed_count() == 0
    assert calls == []


def test_bad_fake_response_consumes_budget(tmp_path):
    gate = fixture(tmp_path, respond=lambda _raw: FakeSseResponse(
        302, "text/event-stream", None, ((SSE, 0),)))
    with pytest.raises(SseResponseDenied):
        request(gate)
    assert gate.store.consumed_count() == 1


def test_prompt_content_is_not_persisted_in_budget_store(tmp_path):
    secret = "PRIVATE_SENTINEL_DO_NOT_RECORD"
    gate = fixture(tmp_path)
    request(gate, body=body(secret))
    assert secret.encode() not in gate.store.path.read_bytes()


def test_gateway_has_no_listener_or_upstream_runtime_capability():
    source = inspect.getsource(__import__(
        "tools.ea4e92dw_kilo_dynamic_fake_gateway", fromlist=["*"]))
    assert not any(term in source for term in (
        "subprocess", "http.server", "socket", "requests", "urllib", "popen"))
