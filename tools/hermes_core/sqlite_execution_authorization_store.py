"""SQLite implementation of the execution-authority store (EA-2).

Persistence/integrity only. NO issuance, NO claim, NO worker, NO execution
transition. Stores immutable EA-1 domain artifacts in a database *separate*
from governance.db, and maintains an append-only, hash-linked authority ledger
in the same DB.

Conventions mirror the governance store:
- PRAGMA foreign_keys=ON; journal_mode=DELETE; busy_timeout=5000
- single-row schema-version table (fail-closed on mismatch / unsupported)
- artifact + ledger event are written atomically (commit/rollback)
- hash verification on write (artifact.verify_hash) and on load (recompute vs
  stored artifact_hash)
- corruption raises ExecutionAuthorizationIntegrityError (never None/false)
- missing record returns None (distinct from corruption)

Design source of truth:
    docs/architecture/hermes-execution-authorization-handoff.md
    docs/architecture/decisions/ADR-0013-execution-authority-separate-from-governance.md
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .execution_authorization import (
    ExecutionAuthorization,
    ExecutionAuthorizationDecision,
    ExecutionAuthorizationRequest,
    reconstruct_authorization,
    reconstruct_decision,
    reconstruct_request,
)
from .execution_authorization_store import (
    ExecutionAuthorizationConflictError,
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationSchemaError,
    ExecutionAuthorizationStore,
    ExecutionAuthorityLedgerEntry,
    IntegrityReport,
)
from .hashing import canonical_json, sha256_payload, sha256_text

SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})


def _hash_decision_linkage(decision_id: str, authorization_id: Optional[str]) -> str:
    """Hash-bound persistence envelope for the non-hash-bound authorization_id
    linkage.

    The Decision artifact hash intentionally excludes authorization_id to keep
    the identity graph acyclic (EA-3A Model A). The PERSISTED linkage must still
    be tamper-evident, so the (decision_id, authorization_id) pair is bound in a
    dedicated envelope hash stored alongside the artifact. Altering the column
    after the fact breaks the envelope, which is detected on load and during
    verify_integrity. authorization_id NULL (DENIED) is covered (not a wildcard).
    """
    payload = {"decision_id": decision_id, "authorization_id": authorization_id}
    return sha256_text(canonical_json(payload))

LEDGER_EVENTS = (
    "REQUEST_RECORDED",
    "DECISION_RECORDED",
    "AUTHORIZATION_RECORDED",
)


def _hash_event(
    sequence_no: int,
    event_type: str,
    artifact_type: str,
    artifact_id: str,
    artifact_hash: str,
    payload_sha256: str,
    previous_entry_sha256: Optional[str],
    timestamp: str,
) -> str:
    """Deterministic entry hash for the authority ledger (chain link)."""
    payload = {
        "sequence_no": sequence_no,
        "event_type": event_type,
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "artifact_hash": artifact_hash,
        "payload_sha256": payload_sha256,
        "previous_entry_sha256": previous_entry_sha256,
        "timestamp": timestamp,
    }
    return sha256_text(canonical_json(payload))


class SQLiteExecutionAuthorizationStore(ExecutionAuthorizationStore):
    """SQLite-backed execution-authority store (EA-2)."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        # Parent directory is created only at open time (no resolver side effect).
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = DELETE")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._initialize()

    # -- schema -------------------------------------------------------------
    def _initialize(self) -> None:
        cur = self._conn
        cur.execute(
            "CREATE TABLE IF NOT EXISTS authority_schema_version (version INTEGER)"
        )
        # Idempotent bootstrap: insert v1 only if no row exists.
        cur.execute(
            "INSERT OR IGNORE INTO authority_schema_version (version) "
            "SELECT ? WHERE NOT EXISTS (SELECT 1 FROM authority_schema_version)",
            (SCHEMA_VERSION,),
        )
        stored = cur.execute(
            "SELECT version FROM authority_schema_version LIMIT 1"
        ).fetchone()
        if stored is None:
            raise ExecutionAuthorizationSchemaError(
                "authority schema version row missing after bootstrap"
            )
        version = int(stored["version"])
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ExecutionAuthorizationSchemaError(
                f"unsupported authority schema version {version}; "
                f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_authorization_requests (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_authorization_decisions (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                authorization_id TEXT,
                decision_linkage_sha256 TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_authorizations (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS authority_ledger (
                sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_entry_sha256 TEXT,
                entry_sha256 TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _table_for(artifact: Any) -> str:
        if isinstance(artifact, ExecutionAuthorizationRequest):
            return "execution_authorization_requests"
        if isinstance(artifact, ExecutionAuthorizationDecision):
            return "execution_authorization_decisions"
        if isinstance(artifact, ExecutionAuthorization):
            return "execution_authorizations"
        raise TypeError(f"unsupported artifact type: {type(artifact)!r}")

    @staticmethod
    def _artifact_id(artifact: Any) -> str:
        if isinstance(artifact, ExecutionAuthorization):
            return artifact.authorization_id
        if isinstance(artifact, ExecutionAuthorizationRequest):
            return artifact.request_id
        if isinstance(artifact, ExecutionAuthorizationDecision):
            return artifact.decision_id
        raise TypeError(f"unsupported artifact type: {type(artifact)!r}")

    def _persist_artifact(self, artifact: Any, table: str) -> bool:
        """Persist if absent or idempotent-identical. Returns True if a write occurred."""
        if not getattr(artifact, "verify_hash", lambda: False)():
            raise ExecutionAuthorizationIntegrityError(
                f"artifact {self._artifact_id(artifact)} failed hash "
                f"verification; refusing to persist"
            )
        canonical = canonical_json(artifact.to_canonical_dict())
        artifact_id = self._artifact_id(artifact)
        existing = self._conn.execute(
            f"SELECT artifact_hash, canonical_payload FROM {table} WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if existing is not None:
            if existing["artifact_hash"] == artifact.artifact_hash and existing[
                "canonical_payload"
            ] == canonical:
                # Idempotent: identical immutable artifact -> success, no write.
                return False
            raise ExecutionAuthorizationConflictError(
                f"immutable artifact {artifact_id} already persisted with "
                f"conflicting content; refusing to overwrite"
            )
        # EA-3A reconstruction-compat: the Decision's authorization_id is a
        # non-hash-bound forward linkage (excluded from the canonical payload/
        # hash preimage to keep the identity graph acyclic). It is persisted in
        # its own column, and made tamper-evident via a dedicated envelope hash
        # (decision_linkage_sha256) bound to (decision_id, authorization_id).
        # The envelope hash is written with the INSERT so the NOT NULL column is
        # satisfied atomically (no separate UPDATE).
        auth_id = None
        linkage_hash = None
        if table == "execution_authorization_decisions":
            auth_id = getattr(artifact, "authorization_id", None)
            linkage_hash = _hash_decision_linkage(artifact_id, auth_id)
        extra_cols = ", authorization_id, decision_linkage_sha256" if linkage_hash is not None else ""
        extra_vals = (auth_id, linkage_hash) if linkage_hash is not None else ()
        self._conn.execute(
            f"INSERT INTO {table} "
            f"(artifact_id, task_id, artifact_type, artifact_hash, canonical_payload{extra_cols}) "
            f"VALUES (?, ?, ?, ?, ?{', ?, ?' if linkage_hash is not None else ''})",
            (
                artifact_id,
                artifact.task_id,
                type(artifact).__name__,
                artifact.artifact_hash,
                canonical,
                *extra_vals,
            ),
        )
        return True

    def _load_artifact(self, table: str, artifact_id: str) -> Optional[dict[str, Any]]:
        # EA-3A: the decisions table carries a dedicated authorization_id column
        # (non-hash-bound forward linkage) plus a tamper-evident envelope hash
        # (decision_linkage_sha256). Select them only when present.
        extra_cols = (
            ", authorization_id, decision_linkage_sha256"
            if table == "execution_authorization_decisions"
            else ""
        )
        row = self._conn.execute(
            f"SELECT artifact_id, task_id, artifact_type, artifact_hash, "
            f"canonical_payload{extra_cols} FROM {table} WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["canonical_payload"])
        recomputed = sha256_payload(payload)
        if recomputed != row["artifact_hash"]:
            raise ExecutionAuthorizationIntegrityError(
                f"artifact {artifact_id} canonical hash mismatch on load "
                f"(stored {row['artifact_hash']}, recomputed {recomputed})"
            )
        # Reconstruct the full domain object (canonical dict excludes artifact_hash).
        payload["artifact_hash"] = row["artifact_hash"]
        # EA-3A reconstruction-compat: recover the non-hash-bound authorization_id
        # forward linkage from its dedicated column for decisions, and verify its
        # tamper-evident envelope against the stored linkage hash.
        if table == "execution_authorization_decisions":
            # Schema v2 always carries these columns for decisions.
            auth_id = row["authorization_id"]
            expected_linkage = row["decision_linkage_sha256"]
            if expected_linkage is not None:
                actual_linkage = _hash_decision_linkage(artifact_id, auth_id)
                if actual_linkage != expected_linkage:
                    raise ExecutionAuthorizationIntegrityError(
                        f"decision {artifact_id} authorization linkage tamper "
                        f"detected on load (envelope mismatch)"
                    )
            if auth_id is not None:
                payload["authorization_id"] = auth_id
        return payload

    def _append_ledger(
        self,
        event_type: str,
        artifact_type: str,
        artifact_id: str,
        artifact_hash: str,
        payload_sha256: str,
        timestamp: str,
    ) -> None:
        prev = self._conn.execute(
            "SELECT entry_sha256 FROM authority_ledger ORDER BY sequence_no DESC LIMIT 1"
        ).fetchone()
        previous_entry_sha256 = prev["entry_sha256"] if prev is not None else None
        # event_id is a deterministic, unique-enough label (not the auth id).
        event_id = sha256_text(f"{event_type}:{artifact_id}:{timestamp}")[:32]
        sequence_no = (
            self._conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) + 1 AS n FROM authority_ledger"
            ).fetchone()["n"]
        )
        entry_sha256 = _hash_event(
            sequence_no,
            event_type,
            artifact_type,
            artifact_id,
            artifact_hash,
            payload_sha256,
            previous_entry_sha256,
            timestamp,
        )
        self._conn.execute(
            "INSERT INTO authority_ledger "
            "(event_id, event_type, artifact_type, artifact_id, artifact_hash, "
            "payload_sha256, previous_entry_sha256, entry_sha256, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                event_type,
                artifact_type,
                artifact_id,
                artifact_hash,
                payload_sha256,
                previous_entry_sha256,
                entry_sha256,
                timestamp,
            ),
        )

    @staticmethod
    def _now_utc() -> str:
        from datetime import datetime

        return datetime.now(datetime.now().astimezone().tzinfo).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    def _persist_with_ledger(self, artifact: Any, event_type: str) -> None:
        table = self._table_for(artifact)
        canonical = canonical_json(artifact.to_canonical_dict())
        payload_sha256 = sha256_text(canonical)
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            wrote = self._persist_artifact(artifact, table)
            # Only append a ledger event when an actual write happened.
            if wrote:
                self._append_ledger(
                    event_type,
                    type(artifact).__name__,
                    self._artifact_id(artifact),
                    artifact.artifact_hash,
                    payload_sha256,
                    self._now_utc(),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # -- requests -----------------------------------------------------------
    def record_request(self, request: ExecutionAuthorizationRequest) -> None:
        self._persist_with_ledger(request, "REQUEST_RECORDED")

    def get_request(
        self, request_id: str
    ) -> Optional[ExecutionAuthorizationRequest]:
        payload = self._load_artifact("execution_authorization_requests", request_id)
        return reconstruct_request(payload) if payload else None

    # -- decisions ----------------------------------------------------------
    def record_decision(self, decision: ExecutionAuthorizationDecision) -> None:
        self._persist_with_ledger(decision, "DECISION_RECORDED")

    def get_decision(
        self, decision_id: str
    ) -> Optional[ExecutionAuthorizationDecision]:
        payload = self._load_artifact(
            "execution_authorization_decisions", decision_id
        )
        return reconstruct_decision(payload) if payload else None

    # -- authorizations -----------------------------------------------------
    def record_authorization(self, authorization: ExecutionAuthorization) -> None:
        self._persist_with_ledger(authorization, "AUTHORIZATION_RECORDED")

    def get_authorization(
        self, authorization_id: str
    ) -> Optional[ExecutionAuthorization]:
        payload = self._load_artifact("execution_authorizations", authorization_id)
        return reconstruct_authorization(payload) if payload else None

    # -- ledger / integrity -------------------------------------------------
    def get_authority_events(self) -> list[ExecutionAuthorityLedgerEntry]:
        rows = self._conn.execute(
            "SELECT sequence_no, event_id, event_type, artifact_type, artifact_id, "
            "artifact_hash, payload_sha256, previous_entry_sha256, entry_sha256, "
            "timestamp FROM authority_ledger ORDER BY sequence_no ASC"
        ).fetchall()
        return [
            ExecutionAuthorityLedgerEntry(
                event_id=r["event_id"],
                event_type=r["event_type"],
                artifact_type=r["artifact_type"],
                artifact_id=r["artifact_id"],
                artifact_hash=r["artifact_hash"],
                payload_sha256=r["payload_sha256"],
                previous_entry_sha256=r["previous_entry_sha256"],
                entry_sha256=r["entry_sha256"],
                timestamp=r["timestamp"],
            )
            for r in rows
        ]

    def verify_integrity(self) -> IntegrityReport:
        failures: list[str] = []
        # 1) artifact hash re-verification across all three tables.
        for table in (
            "execution_authorization_requests",
            "execution_authorization_decisions",
            "execution_authorizations",
        ):
            for r in self._conn.execute(
                f"SELECT artifact_id, artifact_hash, canonical_payload FROM {table}"
            ):
                try:
                    payload = json.loads(r["canonical_payload"])
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{table} {r['artifact_id']} payload unparseable: {exc}")
                    continue
                if sha256_payload(payload) != r["artifact_hash"]:
                    failures.append(
                        f"{table} {r['artifact_id']} artifact hash mismatch"
                    )
        # 1b) decision authorization-linkage envelope verification. The
        # authorization_id column is non-hash-bound (acyclic graph) but MUST be
        # tamper-evident; verify its envelope hash against the stored value.
        for r in self._conn.execute(
            "SELECT artifact_id, authorization_id, decision_linkage_sha256 "
            "FROM execution_authorization_decisions"
        ):
            try:
                expected = _hash_decision_linkage(
                    r["artifact_id"], r["authorization_id"]
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"execution_authorization_decisions {r['artifact_id']} "
                    f"linkage unhashable: {exc}"
                )
                continue
            if expected != r["decision_linkage_sha256"]:
                failures.append(
                    f"execution_authorization_decisions {r['artifact_id']} "
                    f"authorization linkage tamper detected"
                )
        # 2) ledger chain verification.
        rows = self._conn.execute(
            "SELECT sequence_no, event_type, artifact_type, artifact_id, "
            "artifact_hash, payload_sha256, previous_entry_sha256, entry_sha256, "
            "timestamp FROM authority_ledger ORDER BY sequence_no ASC"
        ).fetchall()
        previous_hash: Optional[str] = None
        expected_seq = 1
        for r in rows:
            if int(r["sequence_no"]) != expected_seq:
                failures.append(
                    f"ledger sequence gap at {r['sequence_no']} (expected {expected_seq})"
                )
            expected_seq += 1
            if r["previous_entry_sha256"] != previous_hash:
                failures.append(f"ledger chain break at sequence {r['sequence_no']}")
            derived = _hash_event(
                int(r["sequence_no"]),
                r["event_type"],
                r["artifact_type"],
                r["artifact_id"],
                r["artifact_hash"],
                r["payload_sha256"],
                r["previous_entry_sha256"],
                r["timestamp"],
            )
            if derived != r["entry_sha256"]:
                failures.append(f"ledger entry hash mismatch at sequence {r['sequence_no']}")
            previous_hash = r["entry_sha256"]
        if failures:
            return IntegrityReport(ok=False, checked=len(rows), failures=tuple(failures))
        return IntegrityReport(ok=True, checked=len(rows))

    # -- lifecycle ----------------------------------------------------------
    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
