"""Isolated SQLite tests for EA-4E.92S durable probe evidence."""

import dataclasses
import sqlite3

import pytest

from tools.ea4e92s_probe_evidence_store import (
    BrokerDeathObservation,
    ProbeCompletion,
    ProbeContract,
    ProbeEvidenceConflict,
    ProbeEvidenceIntegrityError,
    ProbeEvidenceStore,
    ProbeEvidenceStoreError,
    ProbeEvidenceTransitionDenied,
    ProbeStart,
)


H = "a" * 64
CLEANUP = ("TERMINATE_JOB", "CLOSE_THREAD", "CLOSE_PROCESS", "CLOSE_JOB")


def contract(**changes):
    value = ProbeContract(
        envelope_id="ea4e92s-envelope-1",
        governing_commit="1" * 64,
        host_identity_sha256="2" * 64,
        request_id="request-0001",
        probe_id="NQ-12",
        runtime_sha256="3" * 64,
        probe_sha256="4" * 64,
        broker_sha256="5" * 64,
        target_contract_sha256="6" * 64,
        profile_name="HermesProbe",
        appcontainer_sid_sha256="7" * 64,
        expected_outcome="BROKER_DEATH_RECOVERED",
    )
    return dataclasses.replace(value, **changes)


def start(**changes):
    return dataclasses.replace(ProbeStart(11, 22, 33, 100, 200), **changes)


def completion(**changes):
    value = ProbeCompletion("UNKNOWN", H, 150, CLEANUP, False, 1)
    return dataclasses.replace(value, **changes)


def observation(**changes):
    value = BrokerDeathObservation(11, 22, 33, 160, CLEANUP, True, 0)
    return dataclasses.replace(value, **changes)


@pytest.fixture
def store(tmp_path):
    return ProbeEvidenceStore.initialize(tmp_path / "probe-evidence.sqlite3")


def test_initialize_is_explicit_and_restart_durable(tmp_path):
    path = tmp_path / "probe.sqlite3"
    with pytest.raises(ProbeEvidenceStoreError):
        ProbeEvidenceStore(path)
    first = ProbeEvidenceStore.initialize(path)
    first.prepare(contract())
    reopened = ProbeEvidenceStore(path)
    assert reopened.get("request-0001").state == "PREPARED"


def test_prepare_exact_replay_and_conflict(store):
    first = store.prepare(contract())
    assert first.state == "PREPARED"
    assert store.prepare(contract()) == first
    with pytest.raises(ProbeEvidenceConflict):
        store.prepare(contract(runtime_sha256="8" * 64))


def test_one_attempt_per_envelope_probe(store):
    store.prepare(contract())
    with pytest.raises(ProbeEvidenceConflict):
        store.prepare(contract(request_id="request-0002"))
    with pytest.raises(ProbeEvidenceIntegrityError):
        store.prepare(contract(attempt_number=2))


def test_start_exact_replay_and_conflict(store):
    store.prepare(contract())
    first = store.start("request-0001", start())
    assert first.state == "STARTED"
    assert store.start("request-0001", start()) == first
    with pytest.raises(ProbeEvidenceConflict):
        store.start("request-0001", start(process_id=99))


@pytest.mark.parametrize(
    ("value", "state"),
    [
        (completion(outcome="EXPECTED", cleanup_confirmed=True,
                    surviving_owned_processes=0), "PASSED"),
        (completion(outcome="UNEXPECTED", cleanup_confirmed=True,
                    surviving_owned_processes=0), "FAILED"),
        (completion(outcome="UNKNOWN", cleanup_confirmed=True,
                    surviving_owned_processes=0), "UNKNOWN"),
        (completion(outcome="EXPECTED", cleanup_confirmed=False,
                    surviving_owned_processes=0), "UNKNOWN"),
        (completion(outcome="EXPECTED", cleanup_confirmed=True,
                    surviving_owned_processes=1), "UNKNOWN"),
    ],
)
def test_completion_projection_is_fail_closed(store, value, state):
    store.prepare(contract())
    store.start("request-0001", start())
    assert store.complete("request-0001", value).state == state


def test_completion_exact_replay_and_conflict(store):
    store.prepare(contract())
    store.start("request-0001", start())
    value = completion()
    assert store.complete("request-0001", value).state == "UNKNOWN"
    assert store.complete("request-0001", value).state == "UNKNOWN"
    with pytest.raises(ProbeEvidenceConflict):
        store.complete("request-0001", completion(monotonic_end_ns=151))


def test_unknown_blocks_later_prepare_and_start(store):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    with pytest.raises(ProbeEvidenceTransitionDenied, match="blocks"):
        store.prepare(contract(request_id="request-0002", probe_id="NQ-11"))
    with pytest.raises(ProbeEvidenceTransitionDenied, match="blocks"):
        store.assert_no_unknown()


def test_exact_clean_reconciliation_unblocks_continuation(store):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    result = store.reconcile_unknown("request-0001", observation())
    assert result.state == "RECONCILED_CLEAN"
    assert result.reconciliation_count == 1
    store.assert_no_unknown()
    assert store.prepare(contract(
        request_id="request-0002", probe_id="NQ-11")).state == "PREPARED"


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_job_id": 99},
        {"observed_process_id": 99},
        {"observed_thread_id": 99},
    ],
)
def test_reconciliation_requires_exact_owned_identity(store, changes):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    with pytest.raises(ProbeEvidenceConflict, match="identity"):
        store.reconcile_unknown("request-0001", observation(**changes))
    assert store.get("request-0001").state == "UNKNOWN"


def test_nonclean_observation_stays_unknown_then_later_clean_observation_resolves(store):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    first = observation(cleanup_confirmed=False, surviving_owned_processes=1)
    assert store.reconcile_unknown("request-0001", first).state == "UNKNOWN"
    second = observation(monotonic_observed_ns=170)
    result = store.reconcile_unknown("request-0001", second)
    assert result.state == "RECONCILED_CLEAN"
    assert result.reconciliation_count == 2


def test_reconciliation_exact_replay_does_not_append(store):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    value = observation(cleanup_confirmed=False, surviving_owned_processes=1)
    assert store.reconcile_unknown("request-0001", value).reconciliation_count == 1
    assert store.reconcile_unknown("request-0001", value).reconciliation_count == 1


def test_reconciliation_time_must_advance(store):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    store.reconcile_unknown(
        "request-0001", observation(cleanup_confirmed=False,
                                    surviving_owned_processes=1))
    with pytest.raises(ProbeEvidenceConflict, match="monotonic"):
        store.reconcile_unknown(
            "request-0001", observation(monotonic_observed_ns=159))


def test_clean_reconciliation_is_terminal(store):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    store.reconcile_unknown("request-0001", observation())
    with pytest.raises(ProbeEvidenceTransitionDenied):
        store.reconcile_unknown(
            "request-0001", observation(monotonic_observed_ns=170))


@pytest.mark.parametrize("operation", ["complete", "reconcile"])
def test_start_required_before_completion_or_reconciliation(store, operation):
    store.prepare(contract())
    with pytest.raises(ProbeEvidenceTransitionDenied):
        if operation == "complete":
            store.complete("request-0001", completion())
        else:
            store.reconcile_unknown("request-0001", observation())


def test_contract_tamper_is_detected(store):
    store.prepare(contract())
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_runs SET contract_json='{}' WHERE request_id='request-0001'")
    with pytest.raises(ProbeEvidenceIntegrityError, match="checksum"):
        store.get("request-0001")


def test_physical_linkage_tamper_is_detected(store):
    store.prepare(contract())
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_runs SET envelope_id='different' WHERE request_id='request-0001'")
    with pytest.raises(ProbeEvidenceIntegrityError, match="linkage"):
        store.get("request-0001")


def test_reconciliation_payload_tamper_is_detected(store):
    store.prepare(contract())
    store.start("request-0001", start())
    store.complete("request-0001", completion())
    store.reconcile_unknown(
        "request-0001", observation(cleanup_confirmed=False,
                                    surviving_owned_processes=1))
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_reconciliations SET observation_json='{}' "
            "WHERE request_id='request-0001'")
    with pytest.raises(ProbeEvidenceIntegrityError, match="checksum"):
        store.get("request-0001")


def test_projected_state_tamper_is_detected(store):
    store.prepare(contract())
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_runs SET state='PASSED' WHERE request_id='request-0001'")
    with pytest.raises(ProbeEvidenceIntegrityError, match="projection"):
        store.get("request-0001")


def test_schema_version_tamper_is_detected(tmp_path):
    store = ProbeEvidenceStore.initialize(tmp_path / "probe.sqlite3")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_evidence_metadata SET schema_version=99 WHERE singleton=1")
    with pytest.raises(ProbeEvidenceIntegrityError, match="unsupported"):
        ProbeEvidenceStore(store.path)


def test_database_connections_are_closed_on_windows(store):
    store.prepare(contract())
    store.start("request-0001", start())
    renamed = store.path.with_suffix(".moved")
    store.path.rename(renamed)
    renamed.rename(store.path)
