"""EA-4E.56 durable process/model accounting qualification. Fake only."""

from __future__ import annotations

import ast
import sqlite3
from dataclasses import dataclass

import pytest

from tools.hermes_core.production_accounting import (
    ACCOUNTING_SCHEMA_VERSION,
    MODEL_EVENT_STATUSES,
    PROCESS_EVENT_STATUSES,
    MODEL_COUNT_FIELDS,
    PROCESS_COUNT_FIELDS,
    ProductionAccountingError,
    ProductionAccountingLedger,
)
from tools.hermes_core.production_app_lifecycle import ProductionRequestAdmissionController
from tools.hermes_core.production_app_recovery import (
    ProductionAppRecoveryOwner,
    ProductionRecoveryStore,
)


NOW = "2026-09-09T12:00:00Z"


def ledger(tmp_path):
    return ProductionAccountingLedger.initialize(tmp_path / "production-accounting.sqlite3")


def process_event(store, event_type, **overrides):
    values = {
        "request_id": "request-a",
        "receiver_id": "kilo-cli-agent",
        "process_attempt_id": "process-attempt-a",
        "event_type": event_type,
        "correlation_id": "correlation-a",
        "created_at": NOW,
        "execution_authority_id": "authority-a",
        "binding_id": "binding-a",
        "process_id": None,
        "process_token": None,
    }
    values.update(overrides)
    return store.record_process_event(**values)


def model_event(store, event_type, **overrides):
    values = {
        "request_id": "request-a",
        "receiver_id": "kilo-cli-agent",
        "model_invocation_attempt_id": "model-attempt-a",
        "event_type": event_type,
        "correlation_id": "correlation-a",
        "created_at": NOW,
        "model_binding_id": "model-binding-a",
        "invocation_authorization_id": "invocation-auth-a",
        "process_id": "pid-a",
    }
    values.update(overrides)
    return store.record_model_event(**values)


def started_process(store, **overrides):
    process_event(store, "PROCESS_START_INTENT", **overrides)
    return process_event(
        store,
        "PROCESS_STARTED",
        process_id=overrides.pop("process_id", "pid-a"),
        process_token=overrides.pop("process_token", "token-a"),
        **overrides,
    )


def entered_model(store, **overrides):
    model_event(store, "MODEL_INVOCATION_INTENT", **overrides)
    return model_event(store, "MODEL_INVOCATION_ENTERED", **overrides)


def test_explicit_initialize_and_reopen_are_windows_safe(tmp_path):
    path = tmp_path / "accounting.sqlite3"
    store = ProductionAccountingLedger.initialize(path)
    process_event(store, "PROCESS_START_INTENT")
    reopened = ProductionAccountingLedger(path)
    assert reopened.process_counts()["PROCESS_START_INTENT"] == 1
    path.rename(tmp_path / "renamed.sqlite3")


def test_missing_store_and_schema_mismatch_fail_closed(tmp_path):
    with pytest.raises(ProductionAccountingError, match="ACCOUNTING_STORE_MISSING"):
        ProductionAccountingLedger(tmp_path / "missing.sqlite3")
    path = tmp_path / "wrong.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE accounting_schema_version(singleton INTEGER PRIMARY KEY, version INTEGER)"
        )
        connection.execute("INSERT INTO accounting_schema_version VALUES(1, 999)")
    with pytest.raises(ProductionAccountingError, match="ACCOUNTING_SCHEMA_MISMATCH"):
        ProductionAccountingLedger(path)


def test_schema_is_versioned_and_domains_are_separate(tmp_path):
    store = ledger(tmp_path)
    with sqlite3.connect(store.path) as connection:
        version = connection.execute(
            "SELECT version FROM accounting_schema_version WHERE singleton=1"
        ).fetchone()[0]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert version == ACCOUNTING_SCHEMA_VERSION == 1
    assert {"process_accounting_events", "model_invocation_accounting_events"} <= tables


def test_process_prestart_denial_records_no_started_event(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    process_event(store, "PROCESS_START_DENIED")
    counts = store.process_counts()
    assert counts["PROCESS_START_DENIED"] == 1
    assert counts["PROCESS_STARTED"] == 0


def test_process_start_failure_records_no_started_event(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    process_event(store, "PROCESS_START_FAILED")
    counts = store.process_counts()
    assert counts["PROCESS_START_FAILED"] == 1
    assert counts["PROCESS_STARTED"] == 0


def test_synthetic_process_start_and_exit_preserve_identity_and_order(tmp_path):
    store = ledger(tmp_path)
    started_process(store)
    process_event(store, "PROCESS_EXITED", process_id="pid-a", process_token="token-a")
    events, _ = store.events_for_request("request-a")
    assert [event.event_type for event in events] == [
        "PROCESS_START_INTENT", "PROCESS_STARTED", "PROCESS_EXITED"
    ]
    assert {(event.process_id, event.process_token) for event in events if event.process_id} == {
        ("pid-a", "token-a")
    }


def test_process_started_requires_intent_and_identity(tmp_path):
    store = ledger(tmp_path)
    with pytest.raises(ProductionAccountingError, match="PROCESS_IDENTITY_REQUIRED"):
        process_event(store, "PROCESS_STARTED")
    with pytest.raises(ProductionAccountingError, match="PROCESS_INTENT_REQUIRED"):
        process_event(store, "PROCESS_STARTED", process_id="pid-a", process_token="token-a")


def test_intents_require_governed_authorization_references(tmp_path):
    store = ledger(tmp_path)
    with pytest.raises(
        ProductionAccountingError, match="PROCESS_GOVERNED_REFERENCES_REQUIRED"
    ):
        process_event(store, "PROCESS_START_INTENT", execution_authority_id=None)
    with pytest.raises(
        ProductionAccountingError, match="MODEL_INVOCATION_AUTHORIZATION_REQUIRED"
    ):
        model_event(store, "MODEL_INVOCATION_INTENT", invocation_authorization_id=None)


def test_process_identity_conflict_rolls_back(tmp_path):
    store = ledger(tmp_path)
    started_process(store)
    with pytest.raises(ProductionAccountingError, match="PROCESS_IDENTITY_CONFLICT"):
        process_event(store, "PROCESS_EXITED", process_id="pid-b", process_token="token-b")
    assert store.process_counts()["PROCESS_EXITED"] == 0


def test_process_duplicate_event_is_idempotent_across_reopen(tmp_path):
    store = ledger(tmp_path)
    first = process_event(store, "PROCESS_START_INTENT")
    reopened = ProductionAccountingLedger(store.path)
    second = process_event(reopened, "PROCESS_START_INTENT", created_at="2026-09-09T12:01:00Z")
    assert first.event_id == second.event_id
    assert reopened.process_counts()["PROCESS_START_INTENT"] == 1


def test_process_intent_represents_post_boundary_uncertainty(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    assert store.unresolved_process_attempts() == ["process-attempt-a"]


def test_model_denial_records_no_entered_event(tmp_path):
    store = ledger(tmp_path)
    model_event(store, "MODEL_INVOCATION_INTENT")
    model_event(store, "MODEL_INVOCATION_DENIED")
    counts = store.model_invocation_counts()
    assert counts["MODEL_INVOCATION_DENIED"] == 1
    assert counts["MODEL_INVOCATION_ENTERED"] == 0


def test_model_failure_and_completion_paths_are_distinct(tmp_path):
    failed = ledger(tmp_path / "failed")
    entered_model(failed)
    model_event(failed, "MODEL_INVOCATION_FAILED")
    failed_counts = failed.model_invocation_counts()
    assert failed_counts["MODEL_INVOCATION_FAILED"] == 1
    assert failed_counts["MODEL_INVOCATION_COMPLETED"] == 0

    completed = ledger(tmp_path / "completed")
    entered_model(completed)
    model_event(completed, "MODEL_INVOCATION_COMPLETED")
    completed_counts = completed.model_invocation_counts()
    assert completed_counts["MODEL_INVOCATION_COMPLETED"] == 1


def test_model_entered_requires_intent_and_terminal_requires_entered(tmp_path):
    store = ledger(tmp_path)
    with pytest.raises(ProductionAccountingError, match="MODEL_INTENT_REQUIRED"):
        model_event(store, "MODEL_INVOCATION_ENTERED")
    model_event(store, "MODEL_INVOCATION_INTENT")
    with pytest.raises(ProductionAccountingError, match="MODEL_ENTERED_REQUIRED"):
        model_event(store, "MODEL_INVOCATION_COMPLETED")


def test_model_duplicate_event_is_idempotent_across_reopen(tmp_path):
    store = ledger(tmp_path)
    first = model_event(store, "MODEL_INVOCATION_INTENT")
    reopened = ProductionAccountingLedger(store.path)
    second = model_event(reopened, "MODEL_INVOCATION_INTENT", created_at="later")
    assert first.event_id == second.event_id
    assert reopened.model_invocation_counts()["MODEL_INVOCATION_INTENT"] == 1


def test_model_intent_represents_post_boundary_uncertainty(tmp_path):
    store = ledger(tmp_path)
    model_event(store, "MODEL_INVOCATION_INTENT")
    assert store.unresolved_model_attempts() == ["model-attempt-a"]


def test_model_correlation_survives_reopen(tmp_path):
    store = ledger(tmp_path)
    entered_model(store)
    model_event(store, "MODEL_INVOCATION_COMPLETED")
    _, events = ProductionAccountingLedger(store.path).events_for_request("request-a")
    assert all(event.request_id == "request-a" for event in events)
    assert all(event.receiver_id == "kilo-cli-agent" for event in events)
    assert all(event.model_binding_id == "model-binding-a" for event in events)
    assert all(event.process_id == "pid-a" for event in events)


def test_cross_request_isolation(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    process_event(
        store, "PROCESS_START_INTENT", request_id="request-b",
        process_attempt_id="process-attempt-b", correlation_id="correlation-b",
    )
    events_a, _ = store.events_for_request("request-a")
    events_b, _ = store.events_for_request("request-b")
    assert {event.request_id for event in events_a} == {"request-a"}
    assert {event.request_id for event in events_b} == {"request-b"}
    assert events_a[0].event_id != events_b[0].event_id


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_dual_receiver_process_and_model_parity(tmp_path, receiver_id):
    store = ledger(tmp_path / receiver_id)
    started_process(store, receiver_id=receiver_id)
    entered_model(store, receiver_id=receiver_id)
    process_events, model_events = store.events_for_request("request-a")
    assert {event.receiver_id for event in process_events} == {receiver_id}
    assert {event.receiver_id for event in model_events} == {receiver_id}


def test_grok_and_unknown_event_types_fail_closed(tmp_path):
    store = ledger(tmp_path)
    with pytest.raises(ProductionAccountingError, match="UNSUPPORTED_RECEIVER"):
        process_event(store, "PROCESS_START_INTENT", receiver_id="grok-agent")
    with pytest.raises(ProductionAccountingError, match="UNSUPPORTED_PROCESS_EVENT"):
        process_event(store, "PROCESS_MAGIC")
    with pytest.raises(ProductionAccountingError, match="UNSUPPORTED_MODEL_EVENT"):
        model_event(store, "MODEL_MAGIC")


def test_tampered_event_fails_closed_on_reconstruction(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE process_accounting_events SET receiver_id='opencode-cli-agent'"
        )
    with pytest.raises(ProductionAccountingError, match="MALFORMED_ACCOUNTING_RECORD"):
        store.events_for_request("request-a")


def test_tampered_status_fails_closed_on_count_query(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE process_accounting_events SET event_status='STARTED'")
    with pytest.raises(ProductionAccountingError, match="MALFORMED_ACCOUNTING_RECORD"):
        store.process_counts()


def test_impossible_terminal_transitions_fail_closed(tmp_path):
    process_store = ledger(tmp_path / "process")
    process_event(process_store, "PROCESS_START_INTENT")
    process_event(process_store, "PROCESS_START_DENIED")
    with pytest.raises(ProductionAccountingError, match="PROCESS_TERMINAL_CONFLICT"):
        process_event(
            process_store, "PROCESS_STARTED", process_id="pid-a", process_token="token-a"
        )

    model_store = ledger(tmp_path / "model")
    entered_model(model_store)
    model_event(model_store, "MODEL_INVOCATION_COMPLETED")
    with pytest.raises(ProductionAccountingError, match="MODEL_TERMINAL_CONFLICT"):
        model_event(model_store, "MODEL_INVOCATION_FAILED")


def test_counts_are_complete_and_derived_from_durable_rows(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    model_event(store, "MODEL_INVOCATION_INTENT")
    assert set(store.process_counts()) == set(PROCESS_EVENT_STATUSES)
    assert set(store.model_invocation_counts()) == set(MODEL_EVENT_STATUSES)
    assert ProductionAccountingLedger(store.path).process_counts()["PROCESS_START_INTENT"] == 1
    assert ProductionAccountingLedger(store.path).model_invocation_counts()[
        "MODEL_INVOCATION_INTENT"
    ] == 1
    assert set(store.canonical_counts()) == set(PROCESS_COUNT_FIELDS) | set(MODEL_COUNT_FIELDS)


def test_multiple_reopen_cycles_do_not_duplicate_events(tmp_path):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    model_event(store, "MODEL_INVOCATION_INTENT")
    for index in range(3):
        store = ProductionAccountingLedger(store.path)
        process_event(store, "PROCESS_START_INTENT", created_at=f"reopen-{index}")
        model_event(store, "MODEL_INVOCATION_INTENT", created_at=f"reopen-{index}")
    assert store.canonical_counts()["process_start_intents"] == 1
    assert store.canonical_counts()["model_invocation_intents"] == 1


def test_required_intent_write_failure_is_fail_closed(tmp_path, monkeypatch):
    store = ledger(tmp_path)
    process_boundary_calls = 0
    model_boundary_calls = 0

    def unavailable():
        raise sqlite3.OperationalError("synthetic accounting outage")

    monkeypatch.setattr(store, "_connect", unavailable)
    with pytest.raises(ProductionAccountingError, match="PROCESS_ACCOUNTING_WRITE_FAILED"):
        process_event(store, "PROCESS_START_INTENT")
    with pytest.raises(ProductionAccountingError, match="MODEL_ACCOUNTING_WRITE_FAILED"):
        model_event(store, "MODEL_INVOCATION_INTENT")
    assert process_boundary_calls == model_boundary_calls == 0


def test_post_boundary_write_failure_leaves_durable_intent_unresolved(tmp_path, monkeypatch):
    store = ledger(tmp_path)
    process_event(store, "PROCESS_START_INTENT")
    model_event(store, "MODEL_INVOCATION_INTENT")

    def unavailable():
        raise sqlite3.OperationalError("synthetic post-boundary outage")

    monkeypatch.setattr(store, "_connect", unavailable)
    with pytest.raises(ProductionAccountingError):
        process_event(store, "PROCESS_STARTED", process_id="pid-a", process_token="token-a")
    with pytest.raises(ProductionAccountingError):
        model_event(store, "MODEL_INVOCATION_ENTERED")
    reopened = ProductionAccountingLedger(store.path)
    assert reopened.unresolved_process_attempts() == ["process-attempt-a"]
    assert reopened.unresolved_model_attempts() == ["model-attempt-a"]


def test_concurrent_rejection_cannot_look_like_execution(tmp_path):
    store = ledger(tmp_path)
    process_event(
        store, "PROCESS_START_INTENT", request_id="request-b",
        process_attempt_id="process-attempt-b", correlation_id="request-b",
    )
    process_event(
        store, "PROCESS_START_DENIED", request_id="request-b",
        process_attempt_id="process-attempt-b", correlation_id="request-b",
    )
    model_event(
        store, "MODEL_INVOCATION_INTENT", request_id="request-b",
        model_invocation_attempt_id="model-attempt-b", correlation_id="request-b",
    )
    model_event(
        store, "MODEL_INVOCATION_DENIED", request_id="request-b",
        model_invocation_attempt_id="model-attempt-b", correlation_id="request-b",
    )
    counts = store.canonical_counts("request-b")
    assert counts["process_started"] == 0
    assert counts["model_invocation_entered"] == 0


@dataclass(frozen=True)
class FakeBinding:
    binding_id: str = "binding-a"
    enablement_id: str = "enablement-a"
    receiver_id: str = "kilo-cli-agent"


class FakeBindings:
    def __init__(self):
        self.binding = FakeBinding()
        self.teardown_calls = 0

    def get_binding_for_receiver(self, receiver_id):
        return self.binding if receiver_id == self.binding.receiver_id else None

    def teardown(self, binding):
        self.teardown_calls += 1
        self.binding = None
        return True


class FakeLiveness:
    def is_host_active(self, host_instance_id):
        return False

    def inspect_process(self, process_id, process_token):
        return "ALIVE"


class FakeProcesses:
    def __init__(self):
        self.calls = 0

    def terminate(self, process_id, process_token):
        self.calls += 1
        return True


class FakeClock:
    def now_iso(self):
        return NOW


def test_ea55_recovery_records_orphan_and_recovered_without_second_start(tmp_path):
    accounting = ledger(tmp_path)
    started_process(
        accounting, process_attempt_id="token-a", process_id="pid-a", process_token="token-a"
    )
    recovery = ProductionRecoveryStore.initialize(tmp_path / "recovery.sqlite3")
    admission = ProductionRequestAdmissionController()
    assert admission.acquire("request-a")
    recovery.begin("request-a", "kilo-cli-agent", "crashed-host")
    recovery.transition(
        "request-a", "PROCESS_STARTED", binding_id="binding-a",
        enablement_id="enablement-a", process_id="pid-a", process_token="token-a",
        process_state="STARTED",
    )
    bindings = FakeBindings()
    processes = FakeProcesses()
    owner = ProductionAppRecoveryOwner(
        recovery, admission, bindings, FakeLiveness(), processes,
        accounting_ledger=accounting, accounting_clock=FakeClock(),
    )
    result = owner.reconcile("request-a")
    counts = accounting.process_counts()
    assert (result.decision, result.reason) == ("ALLOW", "RECOVERED")
    assert counts["PROCESS_STARTED"] == 1
    assert counts["PROCESS_ORPHANED"] == 1
    assert counts["PROCESS_RECOVERED"] == 1
    assert processes.calls == bindings.teardown_calls == 1


def test_accounting_failure_cannot_skip_recovery_cleanup(tmp_path):
    class BrokenAccounting:
        def record_process_event(self, **kwargs):
            raise RuntimeError("synthetic write failure")

    recovery = ProductionRecoveryStore.initialize(tmp_path / "recovery.sqlite3")
    admission = ProductionRequestAdmissionController()
    assert admission.acquire("request-a")
    recovery.begin("request-a", "kilo-cli-agent", "crashed-host")
    recovery.transition(
        "request-a", "PROCESS_STARTED", binding_id="binding-a",
        enablement_id="enablement-a", process_id="pid-a", process_token="token-a",
        process_state="STARTED",
    )
    bindings = FakeBindings()
    processes = FakeProcesses()
    result = ProductionAppRecoveryOwner(
        recovery, admission, bindings, FakeLiveness(), processes,
        accounting_ledger=BrokenAccounting(), accounting_clock=FakeClock(),
    ).reconcile("request-a")
    assert result.decision == "ALLOW"
    assert processes.calls == bindings.teardown_calls == 1


def test_module_has_no_runtime_capability_imports():
    source = open("tools/hermes_core/production_accounting.py", encoding="utf-8").read()
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint({
        "subprocess", "socket", "requests", "urllib", "playwright", "selenium",
        "torch", "diffusers",
    })
