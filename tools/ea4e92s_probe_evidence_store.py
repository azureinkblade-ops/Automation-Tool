"""Durable, non-live evidence state for EA-4E.92S containment probes.

This module records reviewed identities and injected observations. It has no
process, native API, network, filesystem-probe, or cleanup capability.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path


SCHEMA_ID = "hermes.ea4e92s-probe-evidence-store/v1"
SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
PROBE_IDS = tuple(f"NQ-{number:02d}" for number in range(1, 13))
TERMINAL_STATES = frozenset({"PASSED", "FAILED", "RECONCILED_CLEAN"})


class ProbeEvidenceStoreError(RuntimeError):
    """Base fail-closed probe-evidence error."""


class ProbeEvidenceConflict(ProbeEvidenceStoreError):
    """A durable identity was replayed with different material."""


class ProbeEvidenceIntegrityError(ProbeEvidenceStoreError):
    """Persisted evidence is malformed or hash-inconsistent."""


class ProbeEvidenceTransitionDenied(ProbeEvidenceStoreError):
    """The requested state transition is not permitted."""


@dataclass(frozen=True)
class ProbeContract:
    envelope_id: str
    governing_commit: str
    host_identity_sha256: str
    request_id: str
    probe_id: str
    runtime_sha256: str
    probe_sha256: str
    broker_sha256: str
    target_contract_sha256: str
    profile_name: str
    appcontainer_sid_sha256: str
    expected_outcome: str
    attempt_number: int = 1


@dataclass(frozen=True)
class ProbeStart:
    job_id: int
    process_id: int
    thread_id: int
    monotonic_start_ns: int
    monotonic_deadline_ns: int


@dataclass(frozen=True)
class ProbeCompletion:
    outcome: str
    observed_result_sha256: str
    monotonic_end_ns: int
    cleanup_order: tuple[str, ...]
    cleanup_confirmed: bool
    surviving_owned_processes: int


@dataclass(frozen=True)
class BrokerDeathObservation:
    observed_job_id: int
    observed_process_id: int
    observed_thread_id: int
    monotonic_observed_ns: int
    cleanup_order: tuple[str, ...]
    cleanup_confirmed: bool
    surviving_owned_processes: int


@dataclass(frozen=True)
class ProbeRecord:
    contract: ProbeContract
    state: str
    start: ProbeStart | None
    completion: ProbeCompletion | None
    reconciliation_count: int


DDL = """
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
"""


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _payload(value) -> tuple[str, str]:
    text = _canonical(asdict(value))
    return text, _sha256(text)


def _require_text(value, label):
    if type(value) is not str or not value or "\0" in value:
        raise ProbeEvidenceIntegrityError(f"{label} is malformed")


def _require_sha256(value, label):
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise ProbeEvidenceIntegrityError(f"{label} is malformed")


def _validate_contract(value):
    if type(value) is not ProbeContract:
        raise ProbeEvidenceIntegrityError("exact probe contract required")
    for field in ("envelope_id", "request_id", "profile_name", "expected_outcome"):
        _require_text(getattr(value, field), field)
    if value.probe_id not in PROBE_IDS:
        raise ProbeEvidenceIntegrityError("probe_id is malformed")
    for field in (
        "governing_commit", "host_identity_sha256", "runtime_sha256",
        "probe_sha256", "broker_sha256", "target_contract_sha256",
        "appcontainer_sid_sha256",
    ):
        _require_sha256(getattr(value, field), field)
    if value.attempt_number != 1:
        raise ProbeEvidenceIntegrityError("exactly one probe attempt is permitted")


def _validate_start(value):
    if type(value) is not ProbeStart:
        raise ProbeEvidenceIntegrityError("exact probe start evidence required")
    for field in ("job_id", "process_id", "thread_id", "monotonic_start_ns"):
        if type(getattr(value, field)) is not int or getattr(value, field) <= 0:
            raise ProbeEvidenceIntegrityError(f"{field} is malformed")
    if (type(value.monotonic_deadline_ns) is not int
            or value.monotonic_deadline_ns <= value.monotonic_start_ns):
        raise ProbeEvidenceIntegrityError("monotonic deadline is malformed")


def _validate_cleanup(order):
    if type(order) is not tuple or not order:
        raise ProbeEvidenceIntegrityError("cleanup order is malformed")
    allowed = {"TERMINATE_JOB", "CLOSE_THREAD", "CLOSE_PROCESS", "CLOSE_JOB"}
    if (any(type(item) is not str or item not in allowed for item in order)
            or len(order) != len(set(order))):
        raise ProbeEvidenceIntegrityError("cleanup order is malformed")


def _validate_completion(value, start):
    if type(value) is not ProbeCompletion:
        raise ProbeEvidenceIntegrityError("exact probe completion required")
    if value.outcome not in {"EXPECTED", "UNEXPECTED", "UNKNOWN"}:
        raise ProbeEvidenceIntegrityError("probe outcome is malformed")
    _require_sha256(value.observed_result_sha256, "observed_result_sha256")
    if type(value.monotonic_end_ns) is not int or value.monotonic_end_ns < start.monotonic_start_ns:
        raise ProbeEvidenceIntegrityError("monotonic end is malformed")
    _validate_cleanup(value.cleanup_order)
    if type(value.cleanup_confirmed) is not bool:
        raise ProbeEvidenceIntegrityError("cleanup confirmation is malformed")
    if type(value.surviving_owned_processes) is not int or value.surviving_owned_processes < 0:
        raise ProbeEvidenceIntegrityError("owned-process count is malformed")


def _validate_observation(value, start):
    if type(value) is not BrokerDeathObservation:
        raise ProbeEvidenceIntegrityError("exact broker-death observation required")
    if (value.observed_job_id, value.observed_process_id, value.observed_thread_id) != (
            start.job_id, start.process_id, start.thread_id):
        raise ProbeEvidenceConflict("reconciliation resource identity mismatch")
    if (type(value.monotonic_observed_ns) is not int
            or value.monotonic_observed_ns < start.monotonic_start_ns):
        raise ProbeEvidenceIntegrityError("reconciliation monotonic time is malformed")
    _validate_cleanup(value.cleanup_order)
    if type(value.cleanup_confirmed) is not bool:
        raise ProbeEvidenceIntegrityError("cleanup confirmation is malformed")
    if type(value.surviving_owned_processes) is not int or value.surviving_owned_processes < 0:
        raise ProbeEvidenceIntegrityError("owned-process count is malformed")


class ProbeEvidenceStore:
    """Explicit-path SQLite owner for value-only probe evidence."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ProbeEvidenceStoreError("probe evidence store does not exist")
        with closing(self._connect()) as connection:
            self._verify_schema(connection)

    @classmethod
    def initialize(cls, path: str | Path):
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return cls(target)
        connection = sqlite3.connect(str(target), isolation_level=None)
        try:
            connection.executescript(DDL)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO probe_evidence_metadata VALUES(1,?,?,?,1)",
                (SCHEMA_ID, SCHEMA_VERSION, str(uuid.uuid4())),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()
            try:
                target.unlink()
            except OSError:
                pass
            raise
        finally:
            connection.close()
        return cls(target)

    def _connect(self):
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw", uri=True,
                isolation_level=None, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            return connection
        except sqlite3.Error as error:
            raise ProbeEvidenceStoreError(str(error)) from error

    @staticmethod
    def _verify_schema(connection):
        try:
            row = connection.execute(
                "SELECT schema_id,schema_version,store_instance_id,store_epoch "
                "FROM probe_evidence_metadata WHERE singleton=1").fetchone()
        except sqlite3.Error as error:
            raise ProbeEvidenceIntegrityError("probe evidence schema is missing") from error
        if row is None or tuple(row)[:2] != (SCHEMA_ID, SCHEMA_VERSION):
            raise ProbeEvidenceIntegrityError("unsupported probe evidence schema")
        _require_text(row["store_instance_id"], "store_instance_id")
        if row["store_epoch"] != 1:
            raise ProbeEvidenceIntegrityError("unsupported probe evidence store epoch")

    @staticmethod
    def _decode(text, checksum, kind):
        if type(text) is not str or _sha256(text) != checksum:
            raise ProbeEvidenceIntegrityError(f"{kind} checksum mismatch")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise ProbeEvidenceIntegrityError(f"{kind} is not JSON") from error
        if _canonical(value) != text:
            raise ProbeEvidenceIntegrityError(f"{kind} is not canonical")
        return value

    def _record(self, row, connection=None):
        contract = ProbeContract(**self._decode(
            row["contract_json"], row["contract_sha256"], "probe contract"))
        _validate_contract(contract)
        start = None
        if row["start_json"] is not None:
            start = ProbeStart(**self._decode(
                row["start_json"], row["start_sha256"], "probe start"))
            _validate_start(start)
        completion = None
        if row["completion_json"] is not None:
            data = self._decode(
                row["completion_json"], row["completion_sha256"], "probe completion")
            data["cleanup_order"] = tuple(data["cleanup_order"])
            completion = ProbeCompletion(**data)
            if start is None:
                raise ProbeEvidenceIntegrityError("completion exists without start")
            _validate_completion(completion, start)
        if (row["request_id"] != contract.request_id
                or row["envelope_id"] != contract.envelope_id
                or row["probe_id"] != contract.probe_id):
            raise ProbeEvidenceIntegrityError("probe physical linkage mismatch")
        if row["reconciliation_count"] < 0:
            raise ProbeEvidenceIntegrityError("reconciliation count is malformed")
        projected_state = "PREPARED" if start is None else "STARTED"
        if completion is not None:
            projected_state = "UNKNOWN"
            if completion.cleanup_confirmed and completion.surviving_owned_processes == 0:
                if completion.outcome == "EXPECTED":
                    projected_state = "PASSED"
                elif completion.outcome == "UNEXPECTED":
                    projected_state = "FAILED"
        if row["reconciliation_count"]:
            if connection is None or start is None or projected_state != "UNKNOWN":
                raise ProbeEvidenceIntegrityError("reconciliation linkage is malformed")
            reconciliations = connection.execute(
                "SELECT * FROM probe_reconciliations WHERE request_id=? ORDER BY sequence_no",
                (row["request_id"],),
            ).fetchall()
            if len(reconciliations) != row["reconciliation_count"]:
                raise ProbeEvidenceIntegrityError("reconciliation sequence is incomplete")
            prior_time = None
            for sequence, reconciliation in enumerate(reconciliations, start=1):
                if reconciliation["sequence_no"] != sequence:
                    raise ProbeEvidenceIntegrityError("reconciliation sequence is malformed")
                data = self._decode(
                    reconciliation["observation_json"],
                    reconciliation["observation_sha256"],
                    "broker-death observation",
                )
                data["cleanup_order"] = tuple(data["cleanup_order"])
                observation = BrokerDeathObservation(**data)
                _validate_observation(observation, start)
                if prior_time is not None and observation.monotonic_observed_ns <= prior_time:
                    raise ProbeEvidenceIntegrityError("reconciliation time is not monotonic")
                prior_time = observation.monotonic_observed_ns
                projected_state = (
                    "RECONCILED_CLEAN"
                    if observation.cleanup_confirmed
                    and observation.surviving_owned_processes == 0
                    else "UNKNOWN"
                )
                if reconciliation["resulting_state"] != projected_state:
                    raise ProbeEvidenceIntegrityError("reconciliation state mismatch")
                if projected_state == "RECONCILED_CLEAN" and sequence != len(reconciliations):
                    raise ProbeEvidenceIntegrityError("terminal reconciliation has later events")
        if row["state"] != projected_state:
            raise ProbeEvidenceIntegrityError("probe state projection mismatch")
        return ProbeRecord(contract, row["state"], start, completion,
                           row["reconciliation_count"])

    def get(self, request_id: str):
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM probe_runs WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ProbeEvidenceTransitionDenied("probe request is not prepared")
            return self._record(row, connection)

    def prepare(self, contract: ProbeContract):
        _validate_contract(contract)
        text, checksum = _payload(contract)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM probe_runs WHERE request_id=? OR "
                    "(envelope_id=? AND probe_id=?)",
                    (contract.request_id, contract.envelope_id, contract.probe_id),
                ).fetchone()
                if row is not None:
                    existing = self._record(row, connection)
                    if existing.contract != contract:
                        raise ProbeEvidenceConflict("probe identity already has different contract")
                    connection.rollback()
                    return existing
                unknown = connection.execute(
                    "SELECT request_id FROM probe_runs WHERE state='UNKNOWN' LIMIT 1"
                ).fetchone()
                if unknown is not None:
                    raise ProbeEvidenceTransitionDenied(
                        "unreconciled unknown probe blocks later preparation")
                connection.execute(
                    "INSERT INTO probe_runs(request_id,envelope_id,probe_id,state,"
                    "contract_json,contract_sha256) VALUES(?,?,?,'PREPARED',?,?)",
                    (contract.request_id, contract.envelope_id, contract.probe_id,
                     text, checksum),
                )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return self.get(contract.request_id)

    def start(self, request_id: str, start: ProbeStart):
        _validate_start(start)
        text, checksum = _payload(start)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM probe_runs WHERE request_id=?", (request_id,)).fetchone()
                if row is None:
                    raise ProbeEvidenceTransitionDenied("probe request is not prepared")
                existing = self._record(row, connection)
                if existing.start is not None:
                    if existing.start != start:
                        raise ProbeEvidenceConflict("probe start replay conflicts")
                    connection.rollback()
                    return existing
                if existing.state != "PREPARED":
                    raise ProbeEvidenceTransitionDenied("probe cannot start from current state")
                unknown = connection.execute(
                    "SELECT request_id FROM probe_runs WHERE state='UNKNOWN' LIMIT 1"
                ).fetchone()
                if unknown is not None:
                    raise ProbeEvidenceTransitionDenied("unreconciled unknown probe blocks start")
                connection.execute(
                    "UPDATE probe_runs SET state='STARTED',start_json=?,start_sha256=? "
                    "WHERE request_id=?", (text, checksum, request_id))
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return self.get(request_id)

    def complete(self, request_id: str, completion: ProbeCompletion):
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM probe_runs WHERE request_id=?", (request_id,)).fetchone()
                if row is None:
                    raise ProbeEvidenceTransitionDenied("probe request is not prepared")
                existing = self._record(row, connection)
                if existing.start is None:
                    raise ProbeEvidenceTransitionDenied("probe has not started")
                _validate_completion(completion, existing.start)
                if existing.completion is not None:
                    if existing.completion != completion:
                        raise ProbeEvidenceConflict("probe completion replay conflicts")
                    connection.rollback()
                    return existing
                if existing.state != "STARTED":
                    raise ProbeEvidenceTransitionDenied("probe cannot complete from current state")
                state = "UNKNOWN"
                if completion.cleanup_confirmed and completion.surviving_owned_processes == 0:
                    state = "PASSED" if completion.outcome == "EXPECTED" else "FAILED"
                    if completion.outcome == "UNKNOWN":
                        state = "UNKNOWN"
                text, checksum = _payload(completion)
                connection.execute(
                    "UPDATE probe_runs SET state=?,completion_json=?,completion_sha256=? "
                    "WHERE request_id=?", (state, text, checksum, request_id))
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return self.get(request_id)

    def reconcile_unknown(self, request_id: str, observation: BrokerDeathObservation):
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM probe_runs WHERE request_id=?", (request_id,)).fetchone()
                if row is None:
                    raise ProbeEvidenceTransitionDenied("probe request is not prepared")
                existing = self._record(row, connection)
                if existing.start is None:
                    raise ProbeEvidenceTransitionDenied("probe has no owned-resource identity")
                _validate_observation(observation, existing.start)
                text, checksum = _payload(observation)
                latest = connection.execute(
                    "SELECT * FROM probe_reconciliations WHERE request_id=? "
                    "ORDER BY sequence_no DESC LIMIT 1", (request_id,)).fetchone()
                if latest is not None and latest["observation_sha256"] == checksum:
                    if latest["observation_json"] != text:
                        raise ProbeEvidenceIntegrityError("reconciliation hash collision")
                    connection.rollback()
                    return existing
                if existing.state != "UNKNOWN":
                    raise ProbeEvidenceTransitionDenied("only unknown probes may be reconciled")
                if latest is not None:
                    prior = self._decode(
                        latest["observation_json"], latest["observation_sha256"],
                        "broker-death observation")
                    if observation.monotonic_observed_ns <= prior["monotonic_observed_ns"]:
                        raise ProbeEvidenceConflict("reconciliation observations must be monotonic")
                sequence = existing.reconciliation_count + 1
                state = (
                    "RECONCILED_CLEAN"
                    if observation.cleanup_confirmed
                    and observation.surviving_owned_processes == 0
                    else "UNKNOWN"
                )
                connection.execute(
                    "INSERT INTO probe_reconciliations VALUES(?,?,?,?,?)",
                    (request_id, sequence, text, checksum, state))
                connection.execute(
                    "UPDATE probe_runs SET state=?,reconciliation_count=? WHERE request_id=?",
                    (state, sequence, request_id))
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return self.get(request_id)

    def assert_no_unknown(self):
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT request_id FROM probe_runs WHERE state='UNKNOWN' LIMIT 1"
            ).fetchone()
        if row is not None:
            raise ProbeEvidenceTransitionDenied(
                f"unreconciled unknown probe blocks continuation: {row['request_id']}")
