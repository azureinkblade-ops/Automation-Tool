"""SQLite-backed implementation of the Hermes ``GovernanceStore``.

This is the single persistence seam for deterministic governance artifacts
(6A/6B/6C/6D). SQLite is the authoritative machine governance store; canonical
serialization remains an internal hashing mechanism and ``.json`` files are not
the record of truth. Obsidian stays human-readable knowledge only; Anytype is a
later operational projection.

Design rules (see plan section 2/26):
  * deterministic domain logic stays SQL-free; SQLite lives only behind this adapter
  * no SQL types / row ids enter deterministic identity
  * foreign keys enabled, explicit transaction boundaries
  * deterministic schema bootstrap with a version table
  * parameterized SQL only; no silent replacement of governance truth
  * SQLite failures wrapped as ``GovernanceSqliteError``
  * identical repeats are idempotent; same identity + different content fails closed
  * stored records are re-verified (hashes re-derived) before read-back/transition
  * the governance event ledger is append-only and hash-linked
  * acceptance never authorizes execution
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .acceptance_artifact import AcceptanceArtifact
from .consensus_disposition import (
    ConsensusDisposition,
    _disposition_document,
)
from .consensus_evaluator import (
    ConsensusEvaluation,
    _evaluation_document,
)
from .finding_normalizer import (
    FindingSource,
    NormalizedFinding,
    NormalizedFindingSet,
)
from .consensus_disposition import _finding_set_document
from .governance_store import (
    GovernanceChain,
    GovernanceConflictError,
    GovernanceEvent,
    GovernanceIntegrityError,
    GovernanceSchemaError,
    GovernanceSqliteError,
    GovernanceStore,
    GovernanceTransitionError,
    IntegrityReport,
)
from .hashing import canonical_json, sha256_payload
from .schemas import SchemaCatalog

SCHEMA_VERSION = 1

# Event types recorded by this store.
EVENT_FINDING_SET = "governance.finding_set.recorded"
EVENT_EVALUATION = "governance.evaluation.recorded"
EVENT_DISPOSITION = "governance.disposition.recorded"
EVENT_ACCEPTANCE = "governance.acceptance.recorded"
EVENT_TRANSITION = "governance.transition.recorded"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return canonical_json(value)


def _from_json(text: str) -> Any:
    return json.loads(text)


def _build_connection(db_path: str | Path) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:  # pragma: no cover - driver failure
        raise GovernanceSqliteError(f"Could not open governance database: {exc}") from exc
    conn.execute("PRAGMA foreign_keys = ON")
    # Single-writer-per-process store: use the rollback journal (DELETE mode)
    # rather than WAL. WAL leaves a -wal file that a freshly reopened connection
    # can read as stale state; DELETE mode guarantees a reopen observes all
    # prior committed writes. This store has no concurrent-reader requirement.
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


def _bootstrap(conn: sqlite3.Connection) -> None:
    """Idempotent schema creation + version stamp. Never drops data."""
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS governance_schema_version (
                version INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS governance_tasks (
                task_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evidence_packages (
                evidence_package_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                package_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS normalized_finding_sets (
                finding_set_sha256 TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                evidence_package_id TEXT NOT NULL,
                review_ids_json TEXT NOT NULL,
                finding_count INTEGER NOT NULL,
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS normalized_findings (
                finding_set_sha256 TEXT NOT NULL,
                finding_key TEXT NOT NULL,
                severity TEXT NOT NULL,
                PRIMARY KEY (finding_set_sha256, finding_key),
                FOREIGN KEY (finding_set_sha256)
                    REFERENCES normalized_finding_sets(finding_set_sha256)
            );

            CREATE TABLE IF NOT EXISTS consensus_evaluations (
                evaluation_sha256 TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                evidence_package_id TEXT NOT NULL,
                finding_set_sha256 TEXT NOT NULL,
                review_ids_json TEXT NOT NULL,
                agreement_class TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL,
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS consensus_dispositions (
                disposition_sha256 TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                evidence_package_id TEXT NOT NULL,
                finding_set_sha256 TEXT NOT NULL,
                evaluation_sha256 TEXT NOT NULL,
                disposition TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL,
                relevant_finding_keys_json TEXT NOT NULL,
                blocking_finding_keys_json TEXT NOT NULL,
                blocking_severities_json TEXT NOT NULL,
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acceptance_artifacts (
                acceptance_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                evidence_package_id TEXT NOT NULL,
                consensus_id TEXT NOT NULL,
                acceptance_sha256 TEXT NOT NULL,
                disposition_sha256 TEXT NOT NULL,
                evaluation_sha256 TEXT NOT NULL,
                finding_set_sha256 TEXT NOT NULL,
                disposition TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL,
                relevant_finding_keys_json TEXT NOT NULL,
                blocking_finding_keys_json TEXT NOT NULL,
                blocking_severities_json TEXT NOT NULL,
                review_ids_json TEXT NOT NULL,
                finding_keys_json TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                authority_json TEXT NOT NULL,
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acceptance_authority (
                acceptance_id TEXT PRIMARY KEY,
                can_authorize_execution INTEGER NOT NULL,
                requires_separate_authorization INTEGER NOT NULL,
                FOREIGN KEY (acceptance_id)
                    REFERENCES acceptance_artifacts(acceptance_id)
            );

            CREATE TABLE IF NOT EXISTS governance_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_no INTEGER NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                subject_sha256 TEXT NOT NULL,
                previous_event_hash TEXT,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS governance_state (
                task_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS governance_evidence (
                evidence_package_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS governance_reviews (
                review_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                evidence_package_id TEXT NOT NULL,
                review_json TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO governance_schema_version (version) "
            "SELECT ? WHERE NOT EXISTS (SELECT 1 FROM governance_schema_version)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise GovernanceSchemaError(f"Schema bootstrap failed: {exc}") from exc


def _assert_version(conn: sqlite3.Connection) -> None:
    try:
        row = conn.execute(
            "SELECT version FROM governance_schema_version LIMIT 1"
        ).fetchone()
    except sqlite3.Error as exc:  # pragma: no cover - driver failure
        raise GovernanceSqliteError(f"Could not read schema version: {exc}") from exc
    if row is None:
        raise GovernanceSchemaError("Governance schema version is not initialized")
    if int(row["version"]) != SCHEMA_VERSION:
        raise GovernanceSchemaError(
            f"Unsupported governance schema version {row['version']}; "
            f"expected {SCHEMA_VERSION}"
        )


# ---------------------------------------------------------------------------
# Domain object (de)serialization for faithful round-trip + re-verification
# ---------------------------------------------------------------------------
# `to_document` captures the COMPLETE dataclass (every field) for storage and
# reconstruction. The canonical `*_document` helpers in the domain modules remain
# the authoritative basis for hash re-verification only.


def _finding_set_to_document(fs: NormalizedFindingSet) -> dict[str, Any]:
    return {
        "task_id": fs.task_id,
        "evidence_package_id": fs.evidence_package_id,
        "review_ids": list(fs.review_ids),
        "findings": [f.as_document() for f in fs.findings],
        "finding_set_sha256": fs.finding_set_sha256,
    }


def _rebuild_finding_set(doc: dict[str, Any]) -> NormalizedFindingSet:
    findings = tuple(
        NormalizedFinding(
            finding_key=f["finding_key"],
            severity=f["severity"],
            summary=f["summary"],
            evidence_refs=tuple(f["evidence_refs"]),
            sources=tuple(FindingSource(**s) for s in f["sources"]),
        )
        for f in doc["findings"]
    )
    return NormalizedFindingSet(
        task_id=doc["task_id"],
        evidence_package_id=doc["evidence_package_id"],
        review_ids=tuple(doc["review_ids"]),
        findings=findings,
        finding_set_sha256=doc["finding_set_sha256"],
    )


def _evaluation_to_document(ev: ConsensusEvaluation) -> dict[str, Any]:
    return {
        "task_id": ev.task_id,
        "evidence_package_id": ev.evidence_package_id,
        "finding_set_sha256": ev.finding_set_sha256,
        "agreement_class": ev.agreement_class,
        "review_ids": list(ev.review_ids),
        "reviewer_agent_ids": list(ev.reviewer_agent_ids),
        "expected_review_count": ev.expected_review_count,
        "finding_agreements": [a.as_document() for a in ev.finding_agreements],
        "recommendations": list(ev.recommendations),
        "recommendation_conflict": ev.recommendation_conflict,
        "reason_codes": list(ev.reason_codes),
        "evaluation_sha256": ev.evaluation_sha256,
    }


def _rebuild_evaluation(doc: dict[str, Any]) -> ConsensusEvaluation:
    from .consensus_evaluator import FindingAgreement

    return ConsensusEvaluation(
        task_id=doc["task_id"],
        evidence_package_id=doc["evidence_package_id"],
        finding_set_sha256=doc["finding_set_sha256"],
        agreement_class=doc["agreement_class"],
        review_ids=tuple(doc["review_ids"]),
        reviewer_agent_ids=tuple(doc["reviewer_agent_ids"]),
        expected_review_count=doc["expected_review_count"],
        finding_agreements=tuple(FindingAgreement(**a) for a in doc["finding_agreements"]),
        recommendations=tuple(doc["recommendations"]),
        recommendation_conflict=doc["recommendation_conflict"],
        reason_codes=tuple(doc["reason_codes"]),
        evaluation_sha256=doc["evaluation_sha256"],
    )


def _disposition_to_document(disp: ConsensusDisposition) -> dict[str, Any]:
    return {
        "task_id": disp.task_id,
        "evidence_package_id": disp.evidence_package_id,
        "finding_set_sha256": disp.finding_set_sha256,
        "evaluation_sha256": disp.evaluation_sha256,
        "agreement_class": disp.agreement_class,
        "disposition": disp.disposition,
        "reason_codes": list(disp.reason_codes),
        "relevant_finding_keys": list(disp.relevant_finding_keys),
        "blocking_finding_keys": list(disp.blocking_finding_keys),
        "blocking_severities": list(disp.blocking_severities),
        "confidence_policy_marker": disp.confidence_policy_marker,
        "disposition_sha256": disp.disposition_sha256,
    }


def _rebuild_disposition(doc: dict[str, Any]) -> ConsensusDisposition:
    return ConsensusDisposition(
        disposition_sha256=doc["disposition_sha256"],
        task_id=doc["task_id"],
        evidence_package_id=doc["evidence_package_id"],
        finding_set_sha256=doc["finding_set_sha256"],
        evaluation_sha256=doc["evaluation_sha256"],
        disposition=doc["disposition"],
        reason_codes=tuple(doc["reason_codes"]),
        relevant_finding_keys=tuple(doc["relevant_finding_keys"]),
        blocking_finding_keys=tuple(doc["blocking_finding_keys"]),
        blocking_severities=tuple(doc["blocking_severities"]),
        agreement_class=doc["agreement_class"],
        confidence_policy_marker=doc["confidence_policy_marker"],
    )


def _acceptance_to_document(acc: AcceptanceArtifact) -> dict[str, Any]:
    return {
        "acceptance_id": acc.acceptance_id,
        "task_id": acc.task_id,
        "evidence_package_id": acc.evidence_package_id,
        "consensus_id": acc.consensus_id,
        "finding_set_sha256": acc.finding_set_sha256,
        "evaluation_sha256": acc.evaluation_sha256,
        "disposition_sha256": acc.disposition_sha256,
        "disposition": acc.disposition,
        "reason_codes": list(acc.reason_codes),
        "relevant_finding_keys": list(acc.relevant_finding_keys),
        "blocking_finding_keys": list(acc.blocking_finding_keys),
        "blocking_severities": list(acc.blocking_severities),
        "review_ids": list(acc.review_ids),
        "finding_keys": list(acc.finding_keys),
        "accepted_at": acc.accepted_at,
        "authority": dict(acc.authority),
        "acceptance_sha256": acc.acceptance_sha256,
    }


def _rebuild_acceptance(doc: dict[str, Any]) -> AcceptanceArtifact:
    return AcceptanceArtifact(
        acceptance_id=doc["acceptance_id"],
        task_id=doc["task_id"],
        evidence_package_id=doc["evidence_package_id"],
        consensus_id=doc["consensus_id"],
        finding_set_sha256=doc["finding_set_sha256"],
        evaluation_sha256=doc["evaluation_sha256"],
        disposition_sha256=doc["disposition_sha256"],
        disposition=doc["disposition"],
        reason_codes=tuple(doc["reason_codes"]),
        relevant_finding_keys=tuple(doc["relevant_finding_keys"]),
        blocking_finding_keys=tuple(doc["blocking_finding_keys"]),
        blocking_severities=tuple(doc["blocking_severities"]),
        review_ids=tuple(doc["review_ids"]),
        finding_keys=tuple(doc["finding_keys"]),
        accepted_at=doc["accepted_at"],
        authority=dict(doc["authority"]),
        acceptance_sha256=doc["acceptance_sha256"],
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class SQLiteGovernanceStore(GovernanceStore):
    """Authoritative SQLite governance store.

    Connection ownership: this store owns the single SQLite connection it opens.
    It is not safe to share across threads; the expected process model is one
    store per process, opened against a dedicated ``.db`` file (tests use
    temporary databases only).
    """

    def __init__(self, db_path: str | Path, catalog: SchemaCatalog) -> None:
        self.db_path = Path(db_path)
        self.catalog = catalog
        self._conn = _build_connection(self.db_path)
        _bootstrap(self._conn)
        _assert_version(self._conn)

    # -- internal helpers --------------------------------------------------

    def _fetch_one(self, sql: str, params: tuple) -> sqlite3.Row | None:
        try:
            return self._conn.execute(sql, params).fetchone()
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Query failed: {exc}") from exc

    @staticmethod
    def _hash_event(
        sequence_no: int,
        task_id: str,
        event_type: str,
        subject_sha256: str,
        previous_event_hash: str | None,
        created_at: str,
    ) -> str:
        return sha256_payload(
            {
                "sequence_no": sequence_no,
                "task_id": task_id,
                "event_type": event_type,
                "subject_sha256": subject_sha256,
                "previous_event_hash": previous_event_hash,
                "created_at": created_at,
            }
        )

    def _next_sequence(self) -> int:
        row = self._fetch_one(
            "SELECT MAX(sequence_no) AS m FROM governance_events", ()
        )
        return (int(row["m"]) if row and row["m"] is not None else 0) + 1

    def _append_event(
        self,
        task_id: str,
        event_type: str,
        subject_sha256: str,
        *,
        created_at: str | None = None,
    ) -> GovernanceEvent:
        created_at = created_at or _now_iso()
        sequence_no = self._next_sequence()
        previous_hash = self._last_event_hash()
        event_hash = self._hash_event(
            sequence_no, task_id, event_type, subject_sha256, previous_hash, created_at
        )
        try:
            cur = self._conn.execute(
                """
                INSERT INTO governance_events
                    (sequence_no, task_id, event_type, subject_sha256,
                     previous_event_hash, event_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence_no,
                    task_id,
                    event_type,
                    subject_sha256,
                    previous_hash,
                    event_hash,
                    created_at,
                ),
            )
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Event append failed: {exc}") from exc
        return GovernanceEvent(
            event_id=cur.lastrowid,
            sequence_no=sequence_no,
            task_id=task_id,
            event_type=event_type,
            subject_sha256=subject_sha256,
            previous_event_hash=previous_hash,
            event_hash=event_hash,
            created_at=created_at,
        )

    def _last_event_hash(self) -> str | None:
        row = self._fetch_one(
            "SELECT event_hash FROM governance_events ORDER BY sequence_no DESC LIMIT 1",
            (),
        )
        return row["event_hash"] if row else None

    def _ensure_task(self, task_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO governance_tasks (task_id, created_at) VALUES (?, ?)",
            (task_id, _now_iso()),
        )

    @staticmethod
    def _conflict(existing: str, incoming: str, label: str) -> None:
        if existing != incoming:
            raise GovernanceConflictError(
                f"{label} identity collision: stored content hash {existing!r} "
                f"differs from incoming {incoming!r}"
            )

    # -- record artifacts (idempotent + conflict-fail-closed) --------------

    def record_finding_set(self, finding_set: NormalizedFindingSet) -> None:
        self._ensure_task(finding_set.task_id)
        doc = _finding_set_to_document(finding_set)
        identity = finding_set.finding_set_sha256
        existing = self._fetch_one(
            "SELECT finding_set_sha256, document_json FROM normalized_finding_sets "
            "WHERE finding_set_sha256 = ?",
            (identity,),
        )
        if existing is not None:
            rebuilt = _rebuild_finding_set(_from_json(existing["document_json"]))
            if sha256_payload(_finding_set_document(rebuilt)) != identity:
                raise GovernanceIntegrityError(
                    f"Stored finding set {identity} failed re-verification"
                )
            return  # idempotent
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO normalized_finding_sets
                        (finding_set_sha256, task_id, evidence_package_id,
                         review_ids_json, finding_count, document_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identity,
                        finding_set.task_id,
                        finding_set.evidence_package_id,
                        _json(list(finding_set.review_ids)),
                        finding_set.finding_count,
                        _json(doc),
                        _now_iso(),
                    ),
                )
                self._conn.executemany(
                    "INSERT OR IGNORE INTO normalized_findings "
                    "(finding_set_sha256, finding_key, severity) VALUES (?, ?, ?)",
                    [(identity, f.finding_key, f.severity) for f in finding_set.findings],
                )
                self._append_event(finding_set.task_id, EVENT_FINDING_SET, identity)
        except sqlite3.IntegrityError as exc:
            self._conflict(self._stored_doc_hash("normalized_finding_sets", identity), identity, "finding set")
            raise GovernanceConflictError(f"Finding set {identity} conflict: {exc}") from exc
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Finding set record failed: {exc}") from exc

    def record_consensus_evaluation(self, evaluation: ConsensusEvaluation) -> None:
        self._ensure_task(evaluation.task_id)
        doc = _evaluation_to_document(evaluation)
        identity = evaluation.evaluation_sha256
        existing = self._fetch_one(
            "SELECT document_json FROM consensus_evaluations WHERE evaluation_sha256 = ?",
            (identity,),
        )
        if existing is not None:
            rebuilt = _rebuild_evaluation(_from_json(existing["document_json"]))
            if sha256_payload(_evaluation_document(rebuilt)) != identity:
                raise GovernanceIntegrityError(
                    f"Stored evaluation {identity} failed re-verification"
                )
            return
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO consensus_evaluations
                        (evaluation_sha256, task_id, evidence_package_id,
                         finding_set_sha256, review_ids_json, agreement_class,
                         reason_codes_json, document_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identity,
                        evaluation.task_id,
                        evaluation.evidence_package_id,
                        evaluation.finding_set_sha256,
                        _json(list(evaluation.review_ids)),
                        evaluation.agreement_class,
                        _json(list(evaluation.reason_codes)),
                        _json(doc),
                        _now_iso(),
                    ),
                )
                self._append_event(evaluation.task_id, EVENT_EVALUATION, identity)
        except sqlite3.IntegrityError as exc:
            raise GovernanceConflictError(f"Evaluation {identity} conflict: {exc}") from exc
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Evaluation record failed: {exc}") from exc

    def record_consensus_disposition(self, disposition: ConsensusDisposition) -> None:
        self._ensure_task(disposition.task_id)
        doc = _disposition_to_document(disposition)
        identity = disposition.disposition_sha256
        existing = self._fetch_one(
            "SELECT document_json FROM consensus_dispositions WHERE disposition_sha256 = ?",
            (identity,),
        )
        if existing is not None:
            rebuilt = _rebuild_disposition(_from_json(existing["document_json"]))
            if sha256_payload(_disposition_document(rebuilt)) != identity:
                raise GovernanceIntegrityError(
                    f"Stored disposition {identity} failed re-verification"
                )
            return
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO consensus_dispositions
                        (disposition_sha256, task_id, evidence_package_id,
                         finding_set_sha256, evaluation_sha256, disposition,
                         reason_codes_json, relevant_finding_keys_json,
                         blocking_finding_keys_json, blocking_severities_json,
                         document_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identity,
                        disposition.task_id,
                        disposition.evidence_package_id,
                        disposition.finding_set_sha256,
                        disposition.evaluation_sha256,
                        disposition.disposition,
                        _json(list(disposition.reason_codes)),
                        _json(list(disposition.relevant_finding_keys)),
                        _json(list(disposition.blocking_finding_keys)),
                        _json(list(disposition.blocking_severities)),
                        _json(doc),
                        _now_iso(),
                    ),
                )
                self._append_event(disposition.task_id, EVENT_DISPOSITION, identity)
        except sqlite3.IntegrityError as exc:
            raise GovernanceConflictError(f"Disposition {identity} conflict: {exc}") from exc
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Disposition record failed: {exc}") from exc

    def record_acceptance(self, acceptance: AcceptanceArtifact) -> None:
        self._ensure_task(acceptance.task_id)
        doc = _acceptance_to_document(acceptance)
        identity = acceptance.acceptance_id
        existing = self._fetch_one(
            "SELECT document_json FROM acceptance_artifacts WHERE acceptance_id = ?",
            (identity,),
        )
        if existing is not None:
            try:
                rebuilt = _rebuild_acceptance(_from_json(existing["document_json"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise GovernanceIntegrityError(
                    f"Stored acceptance {identity} is malformed: {exc}"
                ) from exc
            if sha256_payload(_acceptance_document_safe(rebuilt)) != acceptance.acceptance_sha256:
                raise GovernanceIntegrityError(
                    f"Stored acceptance {identity} failed re-verification"
                )
            return
        authority = acceptance.authority
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO acceptance_artifacts
                        (acceptance_id, task_id, evidence_package_id, consensus_id,
                         acceptance_sha256, disposition_sha256, evaluation_sha256,
                         finding_set_sha256, disposition, reason_codes_json,
                         relevant_finding_keys_json, blocking_finding_keys_json,
                         blocking_severities_json, review_ids_json, finding_keys_json,
                         accepted_at, authority_json, document_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identity,
                        acceptance.task_id,
                        acceptance.evidence_package_id,
                        acceptance.consensus_id,
                        acceptance.acceptance_sha256,
                        acceptance.disposition_sha256,
                        acceptance.evaluation_sha256,
                        acceptance.finding_set_sha256,
                        acceptance.disposition,
                        _json(list(acceptance.reason_codes)),
                        _json(list(acceptance.relevant_finding_keys)),
                        _json(list(acceptance.blocking_finding_keys)),
                        _json(list(acceptance.blocking_severities)),
                        _json(list(acceptance.review_ids)),
                        _json(list(acceptance.finding_keys)),
                        acceptance.accepted_at,
                        _json(authority),
                        _json(doc),
                        _now_iso(),
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO acceptance_authority
                        (acceptance_id, can_authorize_execution,
                         requires_separate_authorization)
                    VALUES (?, ?, ?)
                    """,
                    (
                        identity,
                        1 if authority.get("can_authorize_execution") else 0,
                        1 if authority.get("requires_separate_authorization") else 0,
                    ),
                )
                self._append_event(acceptance.task_id, EVENT_ACCEPTANCE, acceptance.acceptance_sha256)
        except sqlite3.IntegrityError as exc:
            raise GovernanceConflictError(f"Acceptance {identity} conflict: {exc}") from exc
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Acceptance record failed: {exc}") from exc

    def record_evidence_record(self, evidence: dict[str, Any]) -> None:
        """Persist the frozen evidence record (hermes.evidence document)."""
        task_id = evidence.get("task_id")
        evidence_package_id = evidence.get("evidence_package_id")
        if not task_id or not evidence_package_id:
            raise GovernanceStoreError("Evidence record requires task_id and evidence_package_id")
        self._ensure_task(task_id)
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO governance_evidence
                        (evidence_package_id, task_id, evidence_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (evidence_package_id, task_id, _json(evidence), _now_iso()),
                )
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Evidence record failed: {exc}") from exc

    def record_review_documents(self, reviews: list[dict[str, Any]]) -> None:
        """Persist validated review report documents (hermes.review documents)."""
        if not reviews:
            return
        try:
            with self._conn:
                for review in reviews:
                    task_id = review.get("task_id")
                    evidence_package_id = review.get("evidence_package_id")
                    review_id = review.get("review_id")
                    if not (task_id and evidence_package_id and review_id):
                        raise GovernanceStoreError(
                            "Each review requires task_id, evidence_package_id, review_id"
                        )
                    self._ensure_task(task_id)
                    self._conn.execute(
                        """
                        INSERT OR REPLACE INTO governance_reviews
                            (review_id, task_id, evidence_package_id, review_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (review_id, task_id, evidence_package_id, _json(review)),
                    )
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Review record failed: {exc}") from exc

    def _stored_doc_hash(self, table: str, identity: str) -> str:
        # Helper for conflict messaging; returns the stored sha256 if present.
        col = {
            "normalized_finding_sets": "finding_set_sha256",
        }.get(table, "identity")
        row = self._fetch_one(
            f"SELECT {col} AS v FROM {table} WHERE {col} = ?", (identity,)
        )
        return row["v"] if row else "<none>"

    # -- ledger ------------------------------------------------------------

    def append_governance_event(self, event: GovernanceEvent) -> GovernanceEvent:
        # Persisted records already append their own events; this supports
        # external callers needing to append additional governance events.
        try:
            with self._conn:
                return self._append_event(
                    event.task_id, event.event_type, event.subject_sha256,
                    created_at=event.created_at,
                )
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Event append failed: {exc}") from exc

    def load_task_governance_chain(self, task_id: str) -> GovernanceChain:
        fs_row = self._fetch_one(
            "SELECT document_json FROM normalized_finding_sets WHERE task_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        ev_row = self._fetch_one(
            "SELECT document_json FROM consensus_evaluations WHERE task_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        dp_row = self._fetch_one(
            "SELECT document_json FROM consensus_dispositions WHERE task_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        ac_row = self._fetch_one(
            "SELECT document_json FROM acceptance_artifacts WHERE task_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        state_row = self._fetch_one(
            "SELECT state FROM governance_state WHERE task_id = ?", (task_id,)
        )
        events = [
            GovernanceEvent(
                event_id=r["event_id"],
                sequence_no=r["sequence_no"],
                task_id=r["task_id"],
                event_type=r["event_type"],
                subject_sha256=r["subject_sha256"],
                previous_event_hash=r["previous_event_hash"],
                event_hash=r["event_hash"],
                created_at=r["created_at"],
            )
            for r in self._conn.execute(
                "SELECT * FROM governance_events WHERE task_id = ? "
                "ORDER BY sequence_no ASC",
                (task_id,),
            )
        ]

        try:
            chain = GovernanceChain(
                task_id=task_id,
                finding_set=_rebuild_finding_set(_from_json(fs_row["document_json"])) if fs_row else None,
                evaluation=_rebuild_evaluation(_from_json(ev_row["document_json"])) if ev_row else None,
                disposition=_rebuild_disposition(_from_json(dp_row["document_json"])) if dp_row else None,
                acceptance=_rebuild_acceptance(_from_json(ac_row["document_json"])) if ac_row else None,
                governance_state=state_row["state"] if state_row else None,
                events=tuple(events),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GovernanceIntegrityError(
                f"Persisted governance record for task {task_id!r} is malformed: {exc}"
            ) from exc
        # Re-verify every persisted record before handing it back.
        self._verify_chain_objects(chain)
        return chain

    def _verify_chain_objects(self, chain: GovernanceChain) -> None:
        if chain.finding_set is not None:
            if sha256_payload(_finding_set_document(chain.finding_set)) != chain.finding_set.finding_set_sha256:
                raise GovernanceIntegrityError("Persisted finding set failed re-verification")
        if chain.evaluation is not None:
            if sha256_payload(_evaluation_document(chain.evaluation)) != chain.evaluation.evaluation_sha256:
                raise GovernanceIntegrityError("Persisted evaluation failed re-verification")
        if chain.disposition is not None:
            if sha256_payload(_disposition_document(chain.disposition)) != chain.disposition.disposition_sha256:
                raise GovernanceIntegrityError("Persisted disposition failed re-verification")
        if chain.acceptance is not None:
            if sha256_payload(_acceptance_document_safe(chain.acceptance)) != chain.acceptance.acceptance_sha256:
                raise GovernanceIntegrityError("Persisted acceptance failed re-verification")

    def verify_integrity(self) -> IntegrityReport:
        failures: list[str] = []
        rows = list(
            self._conn.execute(
                "SELECT sequence_no, task_id, event_type, subject_sha256, "
                "previous_event_hash, event_hash, created_at "
                "FROM governance_events ORDER BY sequence_no ASC"
            )
        )
        previous_hash: str | None = None
        expected_seq = 1
        for r in rows:
            if int(r["sequence_no"]) != expected_seq:
                failures.append(f"sequence gap at {r['sequence_no']} (expected {expected_seq})")
            expected_seq += 1
            if r["previous_event_hash"] != previous_hash:
                failures.append(f"chain break at sequence {r['sequence_no']}")
            derived = self._hash_event(
                int(r["sequence_no"]),
                r["task_id"],
                r["event_type"],
                r["subject_sha256"],
                r["previous_event_hash"],
                r["created_at"],
            )
            if derived != r["event_hash"]:
                failures.append(f"event hash mismatch at sequence {r['sequence_no']}")
            previous_hash = r["event_hash"]
        if failures:
            return IntegrityReport(ok=False, checked=len(rows), failures=tuple(failures))
        return IntegrityReport(ok=True, checked=len(rows))

    # -- governed state transition ----------------------------------------

    def current_state(self, task_id: str) -> str | None:
        row = self._fetch_one(
            "SELECT state FROM governance_state WHERE task_id = ?", (task_id,)
        )
        return row["state"] if row else None

    # Allowed governance state edges (plan section 12). The application-level
    # state machine owns the broader lifecycle; 6E enforces this governance
    # subset against persisted artifacts.
    _ALLOWED_GOVERNANCE_TRANSITIONS = {
        ("UNDER_REVIEW", "CONSENSUS_CALCULATED"),
        ("CONSENSUS_CALCULATED", "ACCEPTED"),
    }

    def _validate_governance_transition(
        self, chain: "GovernanceChain", from_state: str, to_state: str
    ) -> None:
        if (from_state, to_state) not in self._ALLOWED_GOVERNANCE_TRANSITIONS:
            raise GovernanceTransitionError(
                f"Governance transition {from_state} -> {to_state} is not permitted"
            )
        if chain.disposition is None or chain.acceptance is None:
            raise GovernanceTransitionError(
                "Transition requires a persisted disposition and acceptance"
            )
        # Binding: every persisted artifact must belong to the same task.
        task_id = chain.task_id
        for artifact in (chain.finding_set, chain.evaluation, chain.disposition, chain.acceptance):
            if artifact is not None and getattr(artifact, "task_id", None) != task_id:
                raise GovernanceTransitionError(
                    "Task/evidence binding violation in persisted governance chain"
                )
        # Only an ACCEPTED disposition may advance governance state to ACCEPTED.
        if chain.disposition.disposition != "ACCEPTED":
            raise GovernanceTransitionError(
                f"Disposition {chain.disposition.disposition!r} cannot reach ACCEPTED"
            )
        # Acceptance must never authorize execution (hard boundary).
        authority = chain.acceptance.authority
        if authority.get("can_authorize_execution") is not False:
            raise GovernanceTransitionError("Acceptance must not authorize execution")
        if authority.get("requires_separate_authorization") is not True:
            raise GovernanceTransitionError(
                "Acceptance must require separate execution authorization"
            )
        # Hashes were already re-verified by load_task_governance_chain; a
        # tampered record would have raised GovernanceIntegrityError there.

    def record_transition(
        self,
        task_id: str,
        from_state: str,
        to_state: str,
        *,
        actor: str = "hermes",
    ) -> GovernanceEvent:
        """Advance governance state through a valid, governance-scoped transition.

        The transition is gated by the governance-specific rules in
        ``_validate_governance_transition`` (plan section 12/14): a complete
        upstream chain, an ACCEPTED disposition only, re-verified persisted
        hashes, task/evidence binding, and an authority block that never grants
        execution. The application-level ``state_machine.validate_transition``
        remains the full-lifecycle gate for complete task envelopes; 6E enforces
        the governance subset against persisted artifacts and records the event
        in the SQLite governance ledger. No execution authority is granted:
        ``ACCEPTED`` never transitions to ``AUTHORIZED``/``EXECUTING``.
        """
        chain = self.load_task_governance_chain(task_id)
        self._validate_governance_transition(chain, from_state, to_state)

        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO governance_state (task_id, state, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET state = excluded.state,
                                                    updated_at = excluded.updated_at
                    """,
                    (task_id, to_state, _now_iso()),
                )
                event = self._append_event(
                    task_id, EVENT_TRANSITION, chain.acceptance.acceptance_sha256
                )
                return event
        except sqlite3.Error as exc:  # pragma: no cover - driver failure
            raise GovernanceSqliteError(f"Transition persistence failed: {exc}") from exc

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        try:
            # Checkpoint the WAL so a subsequently reopened connection observes
            # all committed writes (important for tests that close then reopen).
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:  # pragma: no cover - best effort
            pass
        try:
            self._conn.close()
        except sqlite3.Error:  # pragma: no cover
            pass

    def __enter__(self) -> "SQLiteGovernanceStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _acceptance_document_safe(artifact: AcceptanceArtifact) -> dict[str, Any]:
    """Re-derive the hashed shape of an acceptance artifact for verification."""
    from .acceptance_artifact import _acceptance_document

    return _acceptance_document(artifact)
