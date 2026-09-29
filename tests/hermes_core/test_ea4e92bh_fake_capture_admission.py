from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib

import pytest

from tools.ea4e92bh_fake_capture_admission import (
    CaptureAdmissionDenied, CaptureOnlyScope, FakeCaptureAdmission,
    FakeCaptureEvidence, provision_fake_capture_budget,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore, DurableAuthorizationStoreConflict,
    DurableAuthorizationStoreUnavailable,
)


TASK = b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files."
NOW = "2026-09-29T00:00:01Z"


def fixture(root, capture):
    scope = CaptureOnlyScope(
        run_id="fixture-run", receiver_id="opencode-cli-agent",
        source_commit="a" * 40, executable_sha256="b" * 64,
        config_sha256="c" * 64, transport_id="d" * 64,
        model_binding_id="e" * 64, task_hash=hashlib.sha256(TASK).hexdigest(),
        provider_budget_id="qualification-budget:fixture-run",
        issued_at="2026-09-29T00:00:00Z", expires_at="2026-09-29T00:05:00Z",
    )
    store = DurableInvocationAuthorizationStore.initialize(
        root / "capture.sqlite3", anchor_path=root / "capture-anchor.json"
    )
    provision_fake_capture_budget(store, scope)
    return FakeCaptureAdmission(store, scope, capture=capture)


def complete(task):
    assert task == TASK
    return FakeCaptureEvidence(b"ok", b"", True, True, True, 1, 1)


def attempt(gate, **changes):
    scope = gate.scope
    values = dict(
        run_id=scope.run_id, receiver_id=scope.receiver_id,
        source_commit=scope.source_commit,
        executable_sha256=scope.executable_sha256,
        config_sha256=scope.config_sha256, transport_id=scope.transport_id,
        model_binding_id=scope.model_binding_id,
        provider_budget_id=scope.provider_budget_id, task=TASK, now=NOW,
    )
    values.update(changes)
    return gate.attempt(**values)


def test_one_fake_capture_then_replay_denied_after_reopen(tmp_path):
    calls = []
    gate = fixture(tmp_path, lambda task: calls.append(task) or complete(task))
    assert attempt(gate).stdout == b"ok"
    reopened = DurableInvocationAuthorizationStore(
        gate.store.path, anchor_path=gate.store.anchor_path
    )
    retry = FakeCaptureAdmission(reopened, gate.scope, capture=complete)
    with pytest.raises(CaptureAdmissionDenied, match="consumed"):
        attempt(retry)
    assert calls == [TASK]


@pytest.mark.parametrize("change", [
    {"run_id": "other"}, {"receiver_id": "kilo-agent"},
    {"source_commit": "f" * 40}, {"executable_sha256": "f" * 64},
    {"config_sha256": "f" * 64}, {"transport_id": "f" * 64},
    {"model_binding_id": "f" * 64}, {"provider_budget_id": "other"},
    {"task": b"other"}, {"task": b""}, {"task": b"x" * 65537},
    {"now": "2026-09-29T00:05:00Z"}, {"cancelled": True},
    {"revoked": True},
])
def test_wrong_scope_denied_before_claim_or_capture(tmp_path, change):
    calls = []
    gate = fixture(tmp_path, lambda task: calls.append(task) or complete(task))
    with pytest.raises(CaptureAdmissionDenied):
        attempt(gate, **change)
    assert calls == []
    assert gate.store.consumed_count() == 0


def test_concurrent_replay_has_one_capture(tmp_path):
    calls = []
    gate = fixture(tmp_path, lambda task: calls.append(task) or complete(task))

    def run(_):
        try:
            return attempt(gate).stdout
        except CaptureAdmissionDenied:
            return b"denied"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(4)))
    assert results.count(b"ok") == 1
    assert results.count(b"denied") == 3
    assert calls == [TASK]


@pytest.mark.parametrize("changes", [
    {"stdout_complete": False}, {"stderr_complete": False},
    {"cleanup_confirmed": False}, {"process_start_count": 2},
    {"provider_call_count": 2}, {"provider_call_count": 0},
    {"stdout": b""},
])
def test_incomplete_or_over_budget_stays_consumed(tmp_path, changes):
    gate = fixture(tmp_path, lambda task: replace(complete(task), **changes))
    with pytest.raises(CaptureAdmissionDenied, match="incomplete or over-budget"):
        attempt(gate)
    assert gate.store.consumed_count() == 1
    with pytest.raises(CaptureAdmissionDenied, match="consumed"):
        attempt(gate)


def test_fake_capture_timeout_never_refunds(tmp_path):
    calls = []

    def timeout(task):
        calls.append(task)
        raise TimeoutError("fake timeout")

    gate = fixture(tmp_path, timeout)
    with pytest.raises(TimeoutError, match="fake timeout"):
        attempt(gate)
    with pytest.raises(CaptureAdmissionDenied, match="consumed"):
        attempt(gate)
    assert calls == [TASK]


def test_changed_scope_conflicts_with_provisioned_budget(tmp_path):
    gate = fixture(tmp_path, complete)
    with pytest.raises(DurableAuthorizationStoreConflict):
        provision_fake_capture_budget(
            gate.store, replace(gate.scope, source_commit="f" * 40)
        )


def test_unavailable_anchor_blocks_capture(tmp_path):
    gate = fixture(tmp_path, complete)
    gate.store.anchor_path.rename(tmp_path / "moved-anchor.json")
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        attempt(gate)


def test_missing_budget_and_missing_capture_are_denied(tmp_path):
    gate = fixture(tmp_path, complete)
    with pytest.raises(CaptureAdmissionDenied, match="injected fake capture"):
        FakeCaptureAdmission(gate.store, gate.scope, capture=None)
    other = replace(gate.scope, run_id="other")
    with pytest.raises(CaptureAdmissionDenied, match="provider budget"):
        FakeCaptureAdmission(gate.store, other, capture=complete)


def test_missing_durable_budget_denies_before_capture(tmp_path):
    calls = []
    gate = fixture(tmp_path, lambda task: calls.append(task) or complete(task))
    other = replace(gate.scope, run_id="other", provider_budget_id="qualification-budget:other")
    other_gate = FakeCaptureAdmission(gate.store, other, capture=gate.capture)
    with pytest.raises(CaptureAdmissionDenied, match="consumed"):
        attempt(other_gate)
    assert calls == []
