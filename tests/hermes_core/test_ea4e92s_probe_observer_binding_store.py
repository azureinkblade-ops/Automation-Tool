"""Durable observer-binding schema tests for the NQ-12 evidence store."""

import dataclasses
import hashlib
import json
import sqlite3
from contextlib import closing

import pytest

from tools.ea4e92s_observer_identity import ObserverResourceBinding
from tools.ea4e92s_probe_evidence_store import (
    LEGACY_SCHEMA_ID,
    LEGACY_SCHEMA_VERSION,
    SCHEMA_ID,
    SCHEMA_VERSION,
    ProbeContract,
    ProbeEvidenceConflict,
    ProbeEvidenceIntegrityError,
    ProbeEvidenceStore,
    ProbeEvidenceTransitionDenied,
    ProbeStart,
)


OBSERVER = "12345678-1234-4234-8234-123456789abc"


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


def binding(**changes):
    value = ObserverResourceBinding(
        observer_instance_id=OBSERVER,
        job_token_sha256="8" * 64,
        process_token_sha256="9" * 64,
        thread_token_sha256="a" * 64,
        process_id=22,
        thread_id=33,
        process_creation_time_100ns=123456,
        thread_creation_time_100ns=123457,
        binding_monotonic_ns=150,
    )
    return dataclasses.replace(value, **changes)


@pytest.fixture
def store(tmp_path):
    value = ProbeEvidenceStore.initialize(tmp_path / "probe.sqlite3")
    value.prepare(contract())
    value.start("request-0001", start())
    return value


def _seed_legacy_store(path):
    value = contract()
    payload = json.dumps(
        dataclasses.asdict(value), ensure_ascii=True, separators=(",", ":"),
        sort_keys=True)
    checksum = hashlib.sha256(payload.encode("ascii")).hexdigest()
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
        CREATE TABLE probe_evidence_metadata (
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          schema_id TEXT NOT NULL,
          schema_version INTEGER NOT NULL,
          store_instance_id TEXT NOT NULL,
          store_epoch INTEGER NOT NULL CHECK(store_epoch=1)
        );
        CREATE TABLE probe_runs (
          request_id TEXT PRIMARY KEY,
          envelope_id TEXT NOT NULL,
          probe_id TEXT NOT NULL,
          state TEXT NOT NULL,
          contract_json TEXT NOT NULL,
          contract_sha256 TEXT NOT NULL,
          start_json TEXT,
          start_sha256 TEXT,
          completion_json TEXT,
          completion_sha256 TEXT,
          reconciliation_count INTEGER NOT NULL DEFAULT 0,
          UNIQUE(envelope_id, probe_id)
        );
        CREATE TABLE probe_reconciliations (
          request_id TEXT NOT NULL REFERENCES probe_runs(request_id),
          sequence_no INTEGER NOT NULL,
          observation_json TEXT NOT NULL,
          observation_sha256 TEXT NOT NULL,
          resulting_state TEXT NOT NULL,
          PRIMARY KEY(request_id, sequence_no)
        );
        """)
        connection.execute(
            "INSERT INTO probe_evidence_metadata VALUES(1,?,?,?,1)",
            (LEGACY_SCHEMA_ID, LEGACY_SCHEMA_VERSION, OBSERVER),
        )
        connection.execute(
            "INSERT INTO probe_runs(request_id,envelope_id,probe_id,state,"
            "contract_json,contract_sha256) VALUES(?,?,?,'PREPARED',?,?)",
            (value.request_id, value.envelope_id, value.probe_id, payload, checksum),
        )
        connection.commit()


def test_fresh_store_uses_observer_binding_schema(tmp_path):
    store = ProbeEvidenceStore.initialize(tmp_path / "probe.sqlite3")
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT schema_id,schema_version FROM probe_evidence_metadata"
        ).fetchone() == (SCHEMA_ID, SCHEMA_VERSION)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(probe_runs)")
        }
    assert {"observer_binding_json", "observer_binding_sha256"} <= columns


def test_binding_is_durable_and_exactly_replayable(store):
    first = store.bind_observer(
        "request-0001", binding(), observer_instance_id=OBSERVER)
    assert first.observer_binding == binding()
    assert store.bind_observer(
        "request-0001", binding(), observer_instance_id=OBSERVER) == first
    reopened = ProbeEvidenceStore(store.path)
    assert reopened.require_native_observer_binding(
        "request-0001", observer_instance_id=OBSERVER) == binding()


def test_different_binding_replay_conflicts(store):
    store.bind_observer("request-0001", binding(), observer_instance_id=OBSERVER)
    with pytest.raises(ProbeEvidenceConflict, match="replay"):
        store.bind_observer(
            "request-0001", binding(job_token_sha256="b" * 64),
            observer_instance_id=OBSERVER)


@pytest.mark.parametrize(
    "changes",
    [
        {"process_id": 99},
        {"thread_id": 99},
        {"binding_monotonic_ns": 99},
        {"binding_monotonic_ns": 201},
    ],
)
def test_binding_must_match_start_and_probe_window(store, changes):
    with pytest.raises(ProbeEvidenceIntegrityError):
        store.bind_observer(
            "request-0001", binding(**changes), observer_instance_id=OBSERVER)


def test_binding_requires_exact_expected_observer(store):
    with pytest.raises(ProbeEvidenceIntegrityError, match="observer instance"):
        store.bind_observer(
            "request-0001", binding(),
            observer_instance_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_binding_requires_started_nq12(tmp_path):
    store = ProbeEvidenceStore.initialize(tmp_path / "probe.sqlite3")
    store.prepare(contract())
    with pytest.raises(ProbeEvidenceTransitionDenied, match="started"):
        store.bind_observer(
            "request-0001", binding(), observer_instance_id=OBSERVER)

    other = ProbeEvidenceStore.initialize(tmp_path / "other.sqlite3")
    other.prepare(contract(probe_id="NQ-11"))
    other.start("request-0001", start())
    with pytest.raises(ProbeEvidenceTransitionDenied, match="NQ-12"):
        other.bind_observer(
            "request-0001", binding(), observer_instance_id=OBSERVER)


def test_unbound_record_is_not_native_observer_eligible(store):
    with pytest.raises(ProbeEvidenceTransitionDenied, match="required"):
        store.require_native_observer_binding(
            "request-0001", observer_instance_id=OBSERVER)


def test_binding_tamper_is_detected(store):
    store.bind_observer("request-0001", binding(), observer_instance_id=OBSERVER)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_runs SET observer_binding_json='{}' "
            "WHERE request_id='request-0001'")
    with pytest.raises(ProbeEvidenceIntegrityError, match="checksum"):
        store.get("request-0001")


def test_binding_checksum_removal_is_detected(store):
    store.bind_observer("request-0001", binding(), observer_instance_id=OBSERVER)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_runs SET observer_binding_sha256=NULL "
            "WHERE request_id='request-0001'")
    with pytest.raises(ProbeEvidenceIntegrityError, match="linkage"):
        store.get("request-0001")


def test_hash_consistent_malformed_binding_is_detected(store):
    store.bind_observer("request-0001", binding(), observer_instance_id=OBSERVER)
    payload = "{}"
    checksum = hashlib.sha256(payload.encode("ascii")).hexdigest()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE probe_runs SET observer_binding_json=?,"
            "observer_binding_sha256=? WHERE request_id='request-0001'",
            (payload, checksum),
        )
    with pytest.raises(ProbeEvidenceIntegrityError, match="malformed"):
        store.get("request-0001")


def test_legacy_record_is_migrated_readable_and_not_native_eligible(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    _seed_legacy_store(path)
    store = ProbeEvidenceStore(path)
    assert store.get("request-0001").state == "PREPARED"
    assert store.get("request-0001").observer_binding is None
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT schema_id,schema_version FROM probe_evidence_metadata"
        ).fetchone() == (SCHEMA_ID, SCHEMA_VERSION)
    with pytest.raises(ProbeEvidenceTransitionDenied, match="required"):
        store.require_native_observer_binding(
            "request-0001", observer_instance_id=OBSERVER)


def test_migration_closes_database_connection_on_windows(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    _seed_legacy_store(path)
    ProbeEvidenceStore(path)
    moved = path.with_suffix(".moved")
    path.rename(moved)
    moved.rename(path)
