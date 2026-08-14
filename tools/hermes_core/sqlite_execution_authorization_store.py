"""SQLite implementation of the execution-authority store (EA-2 + EA-3B).

Persistence/integrity only. NO issuance, NO claim, NO worker, NO execution
transition. Stores immutable EA-1 domain artifacts in a database *separate*
from governance.db, and maintains an append-only, hash-linked authority ledger
in the same DB.

EA-3B adds atomic grant persistence and request-keyed lookup primitives
required by the frozen EA-3D issuance design. It does NOT decide whether
authority should be granted, and adds no issuance/claim/worker behavior.

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
    docs/architecture/decisions/ADR-0014-execution-authorization-issuance-trust-boundary.md
    docs/architecture/hermes-execution-authorization-issuance.md
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .execution_authorization import (
    ExecutionAuthorization,
    ExecutionAttempt,
    ExecutionAttemptActor,
    ExecutionAttemptStatus,
    ExecutionClaim,
    ExecutionAuthorizationDecision,
    ExecutionAuthorizationDecisionOutcome,
    ExecutionAuthorizationRequest,
    build_execution_attempt,
    reconstruct_authorization,
    reconstruct_claim,
    reconstruct_decision,
    reconstruct_request,
    reconstruct_attempt,
)
from .execution_authorization_store import (
    ExecutionAuthorizationConflictError,
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationSchemaError,
    ExecutionAuthorizationStore,
    ExecutionAuthorizationStoreError,
    ExecutionAuthorityLedgerEntry,
    IntegrityReport,
)
from .hashing import canonical_json, sha256_payload, sha256_text

SCHEMA_VERSION = 5
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


def _hash_request_linkage(artifact_id: str, request_id: Optional[str]) -> str:
    """Hash-bound persistence envelope for the physical request_id column.

    EA-3B stores request_id physically (outside the canonical payload) to
    support UNIQUE(request_id) and request-keyed lookups. The physical value
    must be tamper-evident, so (artifact_id, request_id) is bound in a dedicated
    envelope hash verified on load and during verify_integrity. Tampering the
    physical column breaks the envelope (fail-closed).
    """
    payload = {"artifact_id": artifact_id, "request_id": request_id}
    return sha256_text(canonical_json(payload))


def _hash_claim_linkage(
    artifact_id: str,
    authorization_id: str,
    authorization_hash: str,
    request_id: str,
    request_hash: str,
    decision_id: str,
    decision_hash: str,
) -> str:
    """Hash-bound tamper-evident envelope for the claim's cryptographic
    lineage to its Authorization/Request/Decision.

    The canonical claim payload excludes artifact_hash (set post-hash), but the
    physical binding columns (authorization_id/hash, request_id/hash,
    decision_id/hash) live OUTSIDE the canonical hash preimage. They are bound
    here so tampering any of them after persistence breaks the envelope,
    detected on load and during verify_integrity.
    """
    payload = {
        "artifact_id": artifact_id,
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "request_id": request_id,
        "request_hash": request_hash,
        "decision_id": decision_id,
        "decision_hash": decision_hash,
    }
    return sha256_text(canonical_json(payload))


def _hash_attempt_linkage(
    artifact_id: str,
    authorization_id: str,
    authorization_hash: str,
    request_id: str,
    request_hash: str,
    decision_id: str,
    decision_hash: str,
    claim_id: str,
    claim_hash: str,
    task_id: str,
    attempt_number: int,
    attempt_actor_id: str,
    attempt_actor_type: str,
    attempt_actor_context: Optional[str],
    attempt_requested_at: str,
    attempt_recorded_at: str,
    claim_expires_at: str,
    must_start_by: str,
    input_hash: str,
    operation: str,
    worker_class: Optional[str],
    status: str,
) -> str:
    """Hash-bound tamper-evident envelope for the attempt's full cryptographic
    lineage.

    The canonical attempt payload excludes artifact_hash (set post-hash), but
    these physical binding columns live OUTSIDE the canonical hash preimage.
    They are bound here so tampering any of them after persistence breaks
    the envelope, detected on load and during verify_integrity.
    """
    payload = {
        "artifact_id": artifact_id,
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "request_id": request_id,
        "request_hash": request_hash,
        "decision_id": decision_id,
        "decision_hash": decision_hash,
        "claim_id": claim_id,
        "claim_hash": claim_hash,
        "task_id": task_id,
        "attempt_number": attempt_number,
        "attempt_actor_id": attempt_actor_id,
        "attempt_actor_type": attempt_actor_type,
        "attempt_actor_context": attempt_actor_context,
        "attempt_requested_at": attempt_requested_at,
        "attempt_recorded_at": attempt_recorded_at,
        "claim_expires_at": claim_expires_at,
        "must_start_by": must_start_by,
        "input_hash": input_hash,
        "operation": operation,
        "worker_class": worker_class,
        "status": status,
    }
    return sha256_text(canonical_json(payload))


LEDGER_EVENTS = (
    "REQUEST_RECORDED",
    "DECISION_RECORDED",
    "AUTHORIZATION_RECORDED",
    "CLAIM_RECORDED",
    "ATTEMPT_RECORDED",
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
    """SQLite-backed execution-authority store (EA-2 + EA-3B)."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        # Parent directory is created only at open time (no resolver side effect).
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = DELETE")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        # Test-only failure-injection seams: when set, the atomic methods raise
        # at specific points to prove rollback leaves zero residue. Never
        # exposed as public API.
        self._fail_after_decision = False
        self._fail_after_attempt_insert = False
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
                request_id TEXT NOT NULL UNIQUE,
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                authorization_id TEXT,
                decision_linkage_sha256 TEXT NOT NULL,
                request_linkage_sha256 TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_authorizations (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                request_linkage_sha256 TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_authorization_claims (
                artifact_id TEXT PRIMARY KEY,
                authorization_id TEXT NOT NULL UNIQUE,
                authorization_hash TEXT NOT NULL,
                request_id TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                decision_hash TEXT NOT NULL,
                task_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                claimed_at TEXT NOT NULL,
                claim_expires_at TEXT NOT NULL,
                claimant_json TEXT NOT NULL,
                artifact_version TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                claim_linkage_sha256 TEXT NOT NULL,
                canonical_payload TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_attempts (
                artifact_id TEXT PRIMARY KEY,
                authorization_id TEXT NOT NULL,
                authorization_hash TEXT NOT NULL,
                request_id TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                decision_hash TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                claim_hash TEXT NOT NULL,
                task_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                attempt_actor_id TEXT NOT NULL,
                attempt_actor_type TEXT NOT NULL,
                attempt_actor_context TEXT,
                attempt_requested_at TEXT NOT NULL,
                attempt_recorded_at TEXT NOT NULL,
                claim_expires_at TEXT NOT NULL,
                must_start_by TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                operation TEXT NOT NULL,
                worker_class TEXT,
                status TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_version TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                attempt_linkage_sha256 TEXT NOT NULL,
                canonical_payload TEXT NOT NULL,
                UNIQUE(authorization_id, attempt_number)
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
        if isinstance(artifact, ExecutionClaim):
            return "execution_authorization_claims"
        if isinstance(artifact, ExecutionAttempt):
            return "execution_attempts"
        raise TypeError(f"unsupported artifact type: {type(artifact)!r}")

    @staticmethod
    def _artifact_id(artifact: Any) -> str:
        if isinstance(artifact, ExecutionAuthorization):
            return artifact.authorization_id
        if isinstance(artifact, ExecutionAuthorizationRequest):
            return artifact.request_id
        if isinstance(artifact, ExecutionAuthorizationDecision):
            return artifact.decision_id
        if isinstance(artifact, ExecutionClaim):
            return artifact.claim_id
        if isinstance(artifact, ExecutionAttempt):
            return artifact.attempt_id
        raise TypeError(f"unsupported artifact type: {type(artifact)!r}")

    def _request_id_for(self, artifact: Any) -> Optional[str]:
        if isinstance(artifact, ExecutionAuthorizationRequest):
            return None  # request_id IS the artifact_id for requests
        return getattr(artifact, "request_id", None)

    def _run_atomic(self, fn) -> Any:
        """Own a single SQLite transaction around fn (no nested commits)."""
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            result = fn()
            self._conn.commit()
            return result
        except Exception:
            self._conn.rollback()
            raise

    def _persist_artifact(self, artifact: Any, table: str) -> bool:
        """Persist if absent or idempotent-identical. Returns True if a write
        occurred. Transaction-neutral: the caller owns the transaction."""
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
        # EA-3A: decisions carry a non-hash-bound authorization_id column plus a
        # tamper-evident envelope (decision_linkage_sha256). EA-3B: decisions and
        # authorizations carry a physical request_id column (UNIQUE) plus a
        # tamper-evident envelope (request_linkage_sha256). All envelope hashes
        # are written with the INSERT so NOT NULL columns are satisfied.
        # The requests table has no request_id column (request_id IS the
        # artifact_id for requests).
        dec_linkage_hash = None
        req_linkage_hash = None
        auth_id = None
        request_id = self._request_id_for(artifact)
        if table == "execution_authorization_decisions":
            auth_id = getattr(artifact, "authorization_id", None)
            dec_linkage_hash = _hash_decision_linkage(artifact_id, auth_id)
            req_linkage_hash = _hash_request_linkage(artifact_id, request_id)
            extra_cols = (
                ", authorization_id, decision_linkage_sha256, request_linkage_sha256"
            )
            extra_vals = (auth_id, dec_linkage_hash, req_linkage_hash)
        elif table == "execution_authorizations":
            req_linkage_hash = _hash_request_linkage(artifact_id, request_id)
            extra_cols = ", request_linkage_sha256"
            extra_vals = (req_linkage_hash,)
        else:
            # execution_authorization_requests: no request_id column.
            extra_cols = ""
            extra_vals = ()
            request_id = None
        # Build the column list without a request_id column for the requests
        # table (request_id is its PRIMARY KEY artifact_id there).
        if table == "execution_authorization_requests":
            col_block = (
                "artifact_id, task_id, artifact_type, artifact_hash, canonical_payload"
            )
            val_block = "?, ?, ?, ?, ?"
            values = (
                artifact_id,
                artifact.task_id,
                type(artifact).__name__,
                artifact.artifact_hash,
                canonical,
                *extra_vals,
            )
        else:
            col_block = (
                "artifact_id, task_id, request_id, artifact_type, artifact_hash, "
                f"canonical_payload{extra_cols}"
            )
            val_block = f"?, ?, ?, ?, ?, ?{', ?' * len(extra_vals)}"
            values = (
                artifact_id,
                artifact.task_id,
                request_id if request_id is not None else "",
                type(artifact).__name__,
                artifact.artifact_hash,
                canonical,
                *extra_vals,
            )
        self._conn.execute(
            f"INSERT INTO {table} ({col_block}) VALUES ({val_block})",
            values,
        )
        return True

    def _load_artifact(self, table: str, artifact_id: str) -> Optional[dict[str, Any]]:
        # Only decisions/authorizations carry physical request_id +
        # request_linkage_sha256 (and decisions also carry authorization_id +
        # decision_linkage_sha256). The requests table has none of these.
        extra_cols = ""
        if table in ("execution_authorization_decisions", "execution_authorizations"):
            extra_cols = ", request_id, request_linkage_sha256"
        if table == "execution_authorization_decisions":
            extra_cols += ", authorization_id, decision_linkage_sha256"
        if table == "execution_authorization_claims":
            # Claims carry physical binding columns (outside the canonical
            # payload hash) bound by a tamper-evident claim_linkage_sha256
            # envelope; read-path validation must fail closed on tampering.
            extra_cols = (
                ", authorization_id, authorization_hash, request_id, "
                "request_hash, decision_id, decision_hash, claim_linkage_sha256"
            )
        if table == "execution_attempts":
            # Attempts carry physical binding columns (outside the canonical
            # payload hash) bound by a tamper-evident attempt_linkage_sha256
            # envelope; read-path validation must fail closed on tampering.
            extra_cols = (
                ", authorization_id, authorization_hash, request_id, "
                "request_hash, decision_id, decision_hash, claim_id, "
                "claim_hash, attempt_number, attempt_actor_id, "
                "attempt_actor_type, attempt_actor_context, "
                "attempt_requested_at, attempt_recorded_at, "
                "claim_expires_at, must_start_by, input_hash, operation, "
                "worker_class, status, attempt_linkage_sha256"
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
        if table in ("execution_authorization_decisions", "execution_authorizations"):
            # Verify the tamper-evident request linkage (physical request_id must
            # match the canonical artifact request_id).
            expected_req = _hash_request_linkage(artifact_id, row["request_id"])
            if expected_req != row["request_linkage_sha256"]:
                raise ExecutionAuthorizationIntegrityError(
                    f"artifact {artifact_id} request linkage tamper detected on load "
                    f"(envelope mismatch)"
                )
        if table == "execution_authorization_decisions":
            # Schema v3 always carries these columns for decisions.
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
        if table == "execution_authorization_claims":
            # Verify the tamper-evident claim linkage (physical authorization/
            # request/decision binding columns must match the envelope).
            expected_claim = _hash_claim_linkage(
                artifact_id,
                row["authorization_id"],
                row["authorization_hash"],
                row["request_id"],
                row["request_hash"],
                row["decision_id"],
                row["decision_hash"],
            )
            if expected_claim != row["claim_linkage_sha256"]:
                raise ExecutionAuthorizationIntegrityError(
                    f"claim {artifact_id} claim linkage tamper detected on load "
                    f"(envelope mismatch)"
                )
        if table == "execution_attempts":
            # Verify the tamper-evident attempt linkage (physical binding
            # columns must match the envelope).
            expected_attempt = _hash_attempt_linkage(
                artifact_id,
                row["authorization_id"],
                row["authorization_hash"],
                row["request_id"],
                row["request_hash"],
                row["decision_id"],
                row["decision_hash"],
                row["claim_id"],
                row["claim_hash"],
                row["task_id"],
                row["attempt_number"],
                row["attempt_actor_id"],
                row["attempt_actor_type"],
                row["attempt_actor_context"],
                row["attempt_requested_at"],
                row["attempt_recorded_at"],
                row["claim_expires_at"],
                row["must_start_by"],
                row["input_hash"],
                row["operation"],
                row["worker_class"],
                row["status"],
            )
            if expected_attempt != row["attempt_linkage_sha256"]:
                raise ExecutionAuthorizationIntegrityError(
                    f"attempt {artifact_id} attempt linkage tamper detected on load "
                    f"(envelope mismatch)"
                )
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
        """Append a hash-linked ledger event. Transaction-neutral."""
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
        """Persist a single artifact + its ledger event in one transaction."""
        canonical = canonical_json(artifact.to_canonical_dict())
        payload_sha256 = sha256_text(canonical)
        table = self._table_for(artifact)

        def _work() -> None:
            wrote = self._persist_artifact(artifact, table)
            if wrote:
                self._append_ledger(
                    event_type,
                    type(artifact).__name__,
                    self._artifact_id(artifact),
                    artifact.artifact_hash,
                    payload_sha256,
                    self._now_utc(),
                )

        self._run_atomic(_work)

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
        """Persist a decision. A GRANTED decision MUST be persisted together with
        its authorization via record_granted_decision_and_authorization (never
        standalone) to prevent a half-grant; only DENIED decisions may be
        persisted on their own."""
        if decision.outcome == ExecutionAuthorizationDecisionOutcome.GRANTED:
            raise ExecutionAuthorizationStoreError(
                "standalone GRANTED decision persistence is not permitted; use "
                "record_granted_decision_and_authorization to persist a GRANTED "
                "decision together with its authorization atomically"
            )
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
        """Standalone authorization persistence is not permitted. An
        ExecutionAuthorization is only valid when persisted atomically with its
        GRANTED decision via record_granted_decision_and_authorization."""
        raise ExecutionAuthorizationStoreError(
            "standalone authorization persistence is not permitted; use "
            "record_granted_decision_and_authorization to persist an "
            "authorization together with its GRANTED decision atomically"
        )

    def get_authorization(
        self, authorization_id: str
    ) -> Optional[ExecutionAuthorization]:
        payload = self._load_artifact("execution_authorizations", authorization_id)
        return reconstruct_authorization(payload) if payload else None

    # -- atomic grant (EA-3B) ----------------------------------------------
    def record_granted_decision_and_authorization(
        self,
        decision: ExecutionAuthorizationDecision,
        authorization: ExecutionAuthorization,
    ) -> None:
        """Atomically persist a GRANTED decision with its authorization.

        Storage-only cross-artifact consistency check. Does NOT decide whether
        the grant is justified; it validates that the two already-built
        immutable artifacts are mutually consistent enough to persist together.
        One SQLite transaction: decision row + DECISION_RECORDED ledger event,
        then authorization row + AUTHORIZATION_RECORDED ledger event. Any
        failure rolls back with zero residue.
        """
        # 1) Cross-artifact consistency (fail closed on any mismatch).
        if decision.outcome != ExecutionAuthorizationDecisionOutcome.GRANTED:
            raise ExecutionAuthorizationStoreError(
                "atomic grant requires a GRANTED decision; DENIED decisions must "
                "be persisted via record_decision"
            )
        mismatches = self._cross_artifact_mismatches(decision, authorization)
        if mismatches:
            raise ExecutionAuthorizationStoreError(
                "atomic grant cross-artifact consistency check failed: "
                + "; ".join(mismatches)
            )

        # 2) Request prerequisite.
        request = self.get_request(decision.request_id)
        if request is None:
            raise ExecutionAuthorizationStoreError(
                f"atomic grant requires a persisted request "
                f"{decision.request_id}; no such request"
            )
        if request.artifact_hash != decision.request_hash:
            raise ExecutionAuthorizationStoreError(
                f"request {decision.request_id} hash mismatch: stored "
                f"{request.artifact_hash}, decision references "
                f"{decision.request_hash}"
            )
        if request.task_id != decision.task_id:
            raise ExecutionAuthorizationStoreError(
                f"request {decision.request_id} task mismatch: stored "
                f"{request.task_id}, decision references {decision.task_id}"
            )
        # Acceptance binding consistency (request <-> authorization). The Decision
        # does not carry acceptance fields; the authorization must agree with the
        # persisted request's governance acceptance binding. Cross-artifact only;
        # we do NOT open governance.db or judge acceptance validity.
        if (request.accepted_governance_artifact_id
                != authorization.accepted_governance_artifact_id):
            raise ExecutionAuthorizationStoreError(
                f"request {decision.request_id} acceptance artifact id mismatch: "
                f"stored {request.accepted_governance_artifact_id}, authorization "
                f"references {authorization.accepted_governance_artifact_id}"
            )
        if (request.accepted_governance_hash
                != authorization.accepted_governance_hash):
            raise ExecutionAuthorizationStoreError(
                f"request {decision.request_id} acceptance hash mismatch: stored "
                f"{request.accepted_governance_hash}, authorization references "
                f"{authorization.accepted_governance_hash}"
            )

        def _work() -> None:
            # Persist decision (idempotent if identical, conflict if different).
            wrote_dec = self._persist_artifact(
                decision, "execution_authorization_decisions"
            )
            if wrote_dec:
                self._append_ledger(
                    "DECISION_RECORDED",
                    type(decision).__name__,
                    decision.decision_id,
                    decision.artifact_hash,
                    sha256_text(canonical_json(decision.to_canonical_dict())),
                    self._now_utc(),
                )
            # Test-only rollback seam.
            if self._fail_after_decision:
                raise ExecutionAuthorizationIntegrityError(
                    "injected failure after decision persistence (rollback test)"
                )
            # Persist authorization.
            wrote_auth = self._persist_artifact(
                authorization, "execution_authorizations"
            )
            if wrote_auth:
                self._append_ledger(
                    "AUTHORIZATION_RECORDED",
                    type(authorization).__name__,
                    authorization.authorization_id,
                    authorization.artifact_hash,
                    sha256_text(canonical_json(authorization.to_canonical_dict())),
                    self._now_utc(),
                )

        try:
            self._run_atomic(_work)
        except sqlite3.IntegrityError as exc:
            # UNIQUE(request_id) violation: a prior terminal decision or
            # authorization already exists for this request.
            raise ExecutionAuthorizationConflictError(
                f"atomic grant conflicts with an existing terminal decision or "
                f"authorization for request {decision.request_id}: {exc}"
            ) from exc

    @staticmethod
    def _cross_artifact_mismatches(
        decision: ExecutionAuthorizationDecision,
        authorization: ExecutionAuthorization,
    ) -> list[str]:
        m: list[str] = []
        if decision.authorization_id != authorization.authorization_id:
            m.append("authorization_id mismatch")
        if decision.request_id != authorization.request_id:
            m.append("request_id mismatch")
        if decision.request_hash != authorization.request_hash:
            m.append("request_hash mismatch")
        if decision.decision_id != authorization.decision_id:
            m.append("decision_id mismatch")
        if decision.artifact_hash != authorization.decision_hash:
            m.append(
                f"decision_hash mismatch (decision {decision.artifact_hash} vs "
                f"authorization.decision_hash {authorization.decision_hash})"
            )
        if decision.task_id != authorization.task_id:
            m.append("task_id mismatch")
        # Policy reference must match (frozen EA-3D design).
        if decision.authorization_policy != authorization.authorization_policy:
            m.append("authorization_policy mismatch")
        return m

    # -- request-keyed reads (EA-3B) ---------------------------------------
    def _get_for_request(
        self, table: str, reconstruct_fn, request_id: str
    ) -> Optional[Any]:
        rows = self._conn.execute(
            f"SELECT artifact_id, request_linkage_sha256 FROM {table} "
            f"WHERE request_id = ?",
            (request_id,),
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            # UNIQUE(request_id) should prevent this, but corruption/manual
            # tampering must fail closed rather than pick an arbitrary row.
            raise ExecutionAuthorizationIntegrityError(
                f"{table} has multiple rows for request_id {request_id}; "
                f"refusing ambiguous read"
            )
        # Reuse the integrity-verified reconstruction path.
        payload = self._load_artifact(table, rows[0]["artifact_id"])
        if payload is None:
            return None
        return reconstruct_fn(payload)

    def get_decision_for_request(
        self, request_id: str
    ) -> Optional[ExecutionAuthorizationDecision]:
        return self._get_for_request(
            "execution_authorization_decisions", reconstruct_decision, request_id
        )

    def get_authorization_for_request(
        self, request_id: str
    ) -> Optional[ExecutionAuthorization]:
        return self._get_for_request(
            "execution_authorizations", reconstruct_authorization, request_id
        )

    # -- claims (EA-4A) ----------------------------------------------------
    def get_claim(
        self, claim_id: str
    ) -> Optional[ExecutionClaim]:
        payload = self._load_artifact("execution_authorization_claims", claim_id)
        return reconstruct_claim(payload) if payload else None

    def get_claim_for_authorization(
        self, authorization_id: str
    ) -> Optional[ExecutionClaim]:
        row = self._conn.execute(
            "SELECT artifact_id FROM execution_authorization_claims "
            "WHERE authorization_id = ?",
            (authorization_id,),
        ).fetchone()
        if row is None:
            return None
        payload = self._load_artifact(
            "execution_authorization_claims", row["artifact_id"]
        )
        return reconstruct_claim(payload) if payload else None

    def claim_authorization_atomically(
        self,
        authorization_id: str,
        claim: ExecutionClaim,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        """Atomically persist a Claim for a valid, unexpired Authorization.

        Storage-level cross-artifact consistency + one-claim-per-authorization
        enforcement. Does NOT decide whether the claim is justified; the claim
        service validates expiry/linkage before calling. One SQLite transaction:
        verify Authorization, reject an existing Claim (UNIQUE authorization_id),
        persist Claim row + CLAIM_RECORDED ledger event. Any failure rolls back
        with zero residue.
        """
        if claim.authorization_id != authorization_id:
            raise ExecutionAuthorizationStoreError(
                f"claim authorization_id {claim.authorization_id} does not match "
                f"requested authorization_id {authorization_id}"
            )
        if not claim.verify_hash():
            raise ExecutionAuthorizationIntegrityError(
                f"claim {claim.claim_id} failed hash verification; refusing to persist"
            )

        from datetime import datetime

        def _work() -> None:
            # 1) Integrity-checked Authorization read (do not trust caller).
            auth = self.get_authorization(authorization_id)
            if auth is None:
                raise ExecutionAuthorizationStoreError(
                    f"claim requires a persisted authorization "
                    f"{authorization_id}; no such authorization"
                )
            if not auth.verify_hash():
                raise ExecutionAuthorizationIntegrityError(
                    f"authorization {authorization_id} failed hash verification"
                )
            # 2) One active claim per Authorization (fail closed on conflict).
            existing = self._conn.execute(
                "SELECT artifact_id FROM execution_authorization_claims "
                "WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            if existing is not None:
                raise ExecutionAuthorizationConflictError(
                    f"authorization {authorization_id} already has a claim "
                    f"({existing['artifact_id']}); at most one claim per authorization"
                )
            # 3) Authorization linkage must match the Claim exactly.
            if auth.authorization_id != claim.authorization_id:
                raise ExecutionAuthorizationIntegrityError("authorization_id mismatch")
            if auth.artifact_hash != claim.authorization_hash:
                raise ExecutionAuthorizationIntegrityError("authorization_hash mismatch")
            if auth.request_id != claim.request_id:
                raise ExecutionAuthorizationIntegrityError("request_id mismatch")
            if auth.request_hash != claim.request_hash:
                raise ExecutionAuthorizationIntegrityError("request_hash mismatch")
            if auth.decision_id != claim.decision_id:
                raise ExecutionAuthorizationIntegrityError("decision_id mismatch")
            if auth.decision_hash != claim.decision_hash:
                raise ExecutionAuthorizationIntegrityError("decision_hash mismatch")
            if auth.task_id != claim.task_id:
                raise ExecutionAuthorizationIntegrityError("task mismatch")
            # 4) Claim-time expiry: claimed_at must be strictly before the
            #    Authorization expiry. (Boundary equality is blocked by the
            #    service; the store re-checks defensively.)
            if auth.expires_at is None:
                raise ExecutionAuthorizationIntegrityError(
                    "authorization expires_at is null; claim blocked"
                )
            claim_time = (clock or self._now_utc)()
            claimed_at_dt = datetime.fromisoformat(claim.claimed_at.replace("Z", "+00:00"))
            auth_expires_dt = datetime.fromisoformat(auth.expires_at.replace("Z", "+00:00"))
            if claimed_at_dt >= auth_expires_dt:
                raise ExecutionAuthorizationIntegrityError(
                    "authorization expired at claim time; claim blocked"
                )
            # 5) Persist Claim + ledger in the same transaction.
            claimant_json = canonical_json(claim.claimant.to_dict())
            linkage = _hash_claim_linkage(
                claim.claim_id,
                claim.authorization_id,
                claim.authorization_hash,
                claim.request_id,
                claim.request_hash,
                claim.decision_id,
                claim.decision_hash,
            )
            canonical = canonical_json(claim.to_canonical_dict())
            payload_sha256 = sha256_text(canonical)
            self._conn.execute(
                "INSERT INTO execution_authorization_claims "
                "(artifact_id, authorization_id, authorization_hash, request_id, "
                "request_hash, decision_id, decision_hash, task_id, artifact_type, "
                "claimed_at, claim_expires_at, claimant_json, artifact_version, "
                "artifact_hash, claim_linkage_sha256, canonical_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim.claim_id,
                    claim.authorization_id,
                    claim.authorization_hash,
                    claim.request_id,
                    claim.request_hash,
                    claim.decision_id,
                    claim.decision_hash,
                    claim.task_id,
                    "ExecutionClaim",
                    claim.claimed_at,
                    claim.claim_expires_at,
                    claimant_json,
                    claim.artifact_version,
                    claim.artifact_hash,
                    linkage,
                    canonical,
                ),
            )
            # Test-only seam (EA-4A rollback proof): if set, raise after the
            # claim row is inserted but before the CLAIM_RECORDED ledger event
            # and commit, so the rollback leaves zero claim/ledger residue.
            if getattr(self, "_fail_after_claim_row", False):
                raise RuntimeError("injected claim-post-insert failure")
            self._append_ledger(
                "CLAIM_RECORDED",
                "ExecutionClaim",
                claim.claim_id,
                claim.artifact_hash,
                payload_sha256,
                claim_time,
            )

        self._run_atomic(_work)

    def try_claim_authorization_atomically(
        self,
        authorization_id: str,
        claim: ExecutionClaim,
        clock: Optional[Callable[[], str]] = None,
    ) -> tuple[bool, Optional[ExecutionClaim]]:
        """Concurrency-safe claim persistence.

        Converts any concurrent-claim outcome into the correct domain result
        instead of a raw exception:

        - first successful write -> ``(False, claim)``;
        - lost ``UNIQUE(authorization_id)`` INSERT race -> re-reads the
          persisted claim and, if it matches this claim's identity/linkage,
          returns ``(True, existing)`` (idempotent, first-writer-wins);
        - in-transaction conflict (the in-transaction ``SELECT`` already sees
          another connection's committed claim) -> re-reads and routes the same
          way: matching identity/linkage -> ``(True, existing)``; different ->
          raises ``ExecutionAuthorizationConflictError`` (CONFLICT, no transfer).
        """
        try:
            self.claim_authorization_atomically(
                authorization_id, claim, clock=clock
            )
        except ExecutionAuthorizationConflictError as exc:
            # In-transaction conflict: another connection already committed a
            # claim for this authorization before this transaction's SELECT
            # finished. Re-read the winner outside the failing transaction and
            # route via the same post-conflict logic.
            existing = self.get_claim_for_authorization(authorization_id)
            if existing is None:
                raise ExecutionAuthorizationConflictError(
                    f"authorization {authorization_id} could not be claimed "
                    f"(no surviving claim)"
                ) from exc
            if (
                existing.claim_id == claim.claim_id
                and existing.authorization_id == claim.authorization_id
                and existing.artifact_hash == claim.artifact_hash
            ):
                return True, existing
            raise ExecutionAuthorizationConflictError(
                f"authorization {authorization_id} already claimed by "
                f"{existing.claimant.claimant_id}; concurrent conflicting "
                f"claim rejected"
            ) from exc
        except sqlite3.IntegrityError as exc:
            # Lost the INSERT race: UNIQUE(authorization_id) fired during
            # insert after the in-transaction SELECT missed the winner's row.
            if "UNIQUE" not in str(exc):
                raise
            existing = self.get_claim_for_authorization(authorization_id)
            if existing is None:
                raise ExecutionAuthorizationConflictError(
                    f"authorization {authorization_id} could not be claimed "
                    f"(unique constraint, no surviving claim)"
                ) from exc
            if (
                existing.claim_id == claim.claim_id
                and existing.authorization_id == claim.authorization_id
                and existing.artifact_hash == claim.artifact_hash
            ):
                return True, existing
            raise ExecutionAuthorizationConflictError(
                f"authorization {authorization_id} already claimed by "
                f"{existing.claimant.claimant_id}; concurrent conflicting "
                f"claim rejected"
            ) from exc
        return False, claim

    # -- execution attempts (EA-4B) ------------------------------------------
    def get_attempt(self, attempt_id: str) -> Optional[ExecutionAttempt]:
        """Load a single ExecutionAttempt by id.

        Read-path integrity validation: artifact hash + physical lineage
        columns verified against the tamper-evident envelope. Tampering any
        physical column after persistence fails closed.
        """
        payload = self._load_artifact("execution_attempts", attempt_id)
        return reconstruct_attempt(payload) if payload else None

    def get_attempts_for_authorization(
        self, authorization_id: str
    ) -> list[ExecutionAttempt]:
        """Load all ExecutionAttempts for an Authorization."""
        rows = self._conn.execute(
            "SELECT artifact_id FROM execution_attempts "
            "WHERE authorization_id = ?",
            (authorization_id,),
        ).fetchall()
        attempts = []
        for r in rows:
            payload = self._load_artifact("execution_attempts", r["artifact_id"])
            if payload is not None:
                attempts.append(reconstruct_attempt(payload))
        return attempts

    def get_attempt_for_claim(self, claim_id: str) -> Optional[ExecutionAttempt]:
        """Load the ExecutionAttempt for a Claim (if exactly one exists)."""
        rows = self._conn.execute(
            "SELECT artifact_id FROM execution_attempts WHERE claim_id = ?",
            (claim_id,),
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise ExecutionAuthorizationIntegrityError(
                f"multiple attempts found for claim {claim_id}"
            )
        payload = self._load_artifact("execution_attempts", rows[0]["artifact_id"])
        return reconstruct_attempt(payload) if payload else None

    def record_attempt(self, attempt: ExecutionAttempt) -> None:
        """Persist an ExecutionAttempt with exactly one ATTEMPT_RECORDED event.

        Low-level persistence primitive. Verifies structural integrity (artifact
        hash + linkage envelope) and validates that the referenced
        Authorization and Claim exist and are integrity-valid. Does NOT decide
        whether a Claim is eligible for consumption (expiry, limit, actor,
        replay) — that policy belongs to consume_claim_transaction().
        """
        if not attempt.verify_hash():
            raise ExecutionAuthorizationIntegrityError(
                f"attempt {attempt.attempt_id} failed hash verification; "
                f"refusing to persist"
            )

        canonical = canonical_json(attempt.to_canonical_dict())
        payload_sha256 = sha256_text(canonical)

        def _work() -> None:
            # Verify referenced Authorization exists and is integrity-valid.
            auth = self.get_authorization(attempt.authorization_id)
            if auth is None:
                raise ExecutionAuthorizationStoreError(
                    f"attempt requires a persisted authorization "
                    f"{attempt.authorization_id}; no such authorization"
                )
            if not auth.verify_hash():
                raise ExecutionAuthorizationIntegrityError(
                    f"authorization {attempt.authorization_id} failed hash "
                    f"verification; attempt blocked"
                )

            # Verify referenced Claim exists and is integrity-valid.
            # The attempt references a specific claim_id; that exact claim must exist.
            claim = self.get_claim(attempt.claim_id)
            if claim is None:
                raise ExecutionAuthorizationStoreError(
                    f"attempt requires a persisted claim "
                    f"{attempt.claim_id}; no such claim"
                )
            if not claim.verify_hash():
                raise ExecutionAuthorizationIntegrityError(
                    f"claim {attempt.claim_id} failed hash verification; "
                    f"attempt blocked"
                )

            # Verify lineage consistency (Claim <-> Attempt).
            if claim.claim_id != attempt.claim_id:
                raise ExecutionAuthorizationLineageError(
                    f"claim_id mismatch: expected {attempt.claim_id}, "
                    f"got {claim.claim_id}"
                )
            # The claim's stored hash is artifact_hash; the attempt references it as claim_hash
            if claim.artifact_hash != attempt.claim_hash:
                raise ExecutionAuthorizationLineageError(
                    f"claim_hash mismatch for claim {attempt.claim_id}"
                )
            if claim.authorization_id != attempt.authorization_id:
                raise ExecutionAuthorizationLineageError(
                    f"claim {claim.claim_id} belongs to authorization "
                    f"{claim.authorization_id}, not "
                    f"{attempt.authorization_id}"
                )
            if claim.authorization_hash != attempt.authorization_hash:
                raise ExecutionAuthorizationLineageError(
                    f"authorization_hash mismatch for authorization "
                    f"{attempt.authorization_id}"
                )
            if claim.request_id != attempt.request_id:
                raise ExecutionAuthorizationLineageError(
                    f"request_id mismatch: claim {claim.request_id}, "
                    f"attempt {attempt.request_id}"
                )
            if claim.request_hash != attempt.request_hash:
                raise ExecutionAuthorizationLineageError(
                    f"request_hash mismatch for request {attempt.request_id}"
                )
            if claim.decision_id != attempt.decision_id:
                raise ExecutionAuthorizationLineageError(
                    f"decision_id mismatch: claim {claim.decision_id}, "
                    f"attempt {attempt.decision_id}"
                )
            if claim.decision_hash != attempt.decision_hash:
                raise ExecutionAuthorizationLineageError(
                    f"decision_hash mismatch for decision {attempt.decision_id}"
                )
            if claim.task_id != attempt.task_id:
                raise ExecutionAuthorizationLineageError(
                    f"task_id mismatch: claim {claim.task_id}, "
                    f"attempt {attempt.task_id}"
                )

            linkage = _hash_attempt_linkage(
                attempt.attempt_id,
                attempt.authorization_id,
                attempt.authorization_hash,
                attempt.request_id,
                attempt.request_hash,
                attempt.decision_id,
                attempt.decision_hash,
                attempt.claim_id,
                attempt.claim_hash,
                attempt.task_id,
                attempt.attempt_number,
                attempt.attempt_actor_id,
                attempt.attempt_actor_type,
                attempt.attempt_actor_context,
                attempt.attempt_requested_at,
                attempt.attempt_recorded_at,
                attempt.claim_expires_at,
                attempt.must_start_by,
                attempt.input_hash,
                attempt.operation,
                attempt.worker_class,
                attempt.status.value,
            )

            # Transaction-neutral INSERT: caller owns the transaction.
            self._insert_attempt_rows(attempt, canonical, payload_sha256, linkage)

        try:
            self._run_atomic(_work)
        except sqlite3.IntegrityError as exc:
            raise ExecutionAuthorizationConflictError(
                f"attempt {attempt.attempt_id} conflicts with an existing "
                f"attempt: {exc}"
            ) from exc

    def _insert_attempt_rows(
        self, attempt: ExecutionAttempt, canonical: str, payload_sha256: str, linkage: str
    ) -> None:
        """Transaction-neutral INSERT of attempt + ledger rows.

        Caller owns the transaction. No BEGIN/COMMIT here.
        """
        self._conn.execute(
            "INSERT INTO execution_attempts "
            "(artifact_id, authorization_id, authorization_hash, request_id, "
            "request_hash, decision_id, decision_hash, claim_id, claim_hash, "
            "task_id, attempt_number, attempt_actor_id, attempt_actor_type, "
            "attempt_actor_context, attempt_requested_at, attempt_recorded_at, "
            "claim_expires_at, must_start_by, input_hash, operation, "
            "worker_class, status, artifact_type, artifact_version, artifact_hash, "
            "attempt_linkage_sha256, canonical_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt.attempt_id,
                attempt.authorization_id,
                attempt.authorization_hash,
                attempt.request_id,
                attempt.request_hash,
                attempt.decision_id,
                attempt.decision_hash,
                attempt.claim_id,
                attempt.claim_hash,
                attempt.task_id,
                attempt.attempt_number,
                attempt.attempt_actor_id,
                attempt.attempt_actor_type,
                attempt.attempt_actor_context,
                attempt.attempt_requested_at,
                attempt.attempt_recorded_at,
                attempt.claim_expires_at,
                attempt.must_start_by,
                attempt.input_hash,
                attempt.operation,
                attempt.worker_class,
                attempt.status.value,
                type(attempt).__name__,
                attempt.artifact_version,
                attempt.artifact_hash,
                linkage,
                canonical,
            ),
        )
        # Test-only failure-injection point: simulates a crash after the attempt
        # INSERT but before the ATTEMPT_RECORDED ledger event, proving that
        # the transaction rolls back to zero residue (no partial write).
        if self._fail_after_attempt_insert:
            raise RuntimeError("injected failure after attempt INSERT")
        self._append_ledger(
            "ATTEMPT_RECORDED",
            type(attempt).__name__,
            attempt.attempt_id,
            attempt.artifact_hash,
            payload_sha256,
            self._now_utc(),
        )

    def consume_claim_transaction(
        self,
        *,
        authorization_id: str,
        claim_id: str,
        claimant: ExecutionAttemptActor,
        must_start_within_seconds: Optional[int] = None,
        clock: Callable[[], str],
    ) -> "ExecutionAttemptResult":
        """Atomically consume a valid ExecutionClaim into a durable ExecutionAttempt.

        The ENTIRE consume — replay check, claim/auth validation, expiry check,
        attempt-limit check, attempt-number assignment, persistence, and
        ATTEMPT_RECORDED ledger event — happens inside a single BEGIN IMMEDIATE
        transaction. This eliminates the TOCTOU race between the read/count and
        the write.

        The attempt limit is derived from the persisted Authorization's scope
        (caller cannot raise the ceiling). Replay identity is the full
        structured actor (actor_id + actor_type + actor_context); any field
        change is a CONFLICT.
        """
        from .execution_authorization_attempt import (
            ExecutionAttemptResult,
            ExecutionAttemptClaimExpiredError,
            ExecutionAttemptLimitError,
            ExecutionAttemptConflictError,
            ExecutionAttemptLineageError,
            ExecutionAttemptError,
        )

        # Pre-transaction validation: actor type check (cheap, no DB needed).
        if not isinstance(claimant, ExecutionAttemptActor):
            raise ExecutionAttemptError("claimant must be an ExecutionAttemptActor")

        now = clock()
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))

        def _work() -> ExecutionAttemptResult:
            # 1) Replay: existing attempt for this claim + full actor identity.
            existing_attempt = self.get_attempt_for_claim(claim_id)
            if existing_attempt is not None:
                # Full structured actor identity must match for replay.
                if (
                    existing_attempt.attempt_actor_id == claimant.actor_id
                    and existing_attempt.attempt_actor_type == claimant.actor_type
                    and existing_attempt.attempt_actor_context == claimant.actor_context
                ):
                    return ExecutionAttemptResult(
                        authorization_id=authorization_id,
                        claim_id=claim_id,
                        attempt_id=existing_attempt.attempt_id,
                        attempt_hash=existing_attempt.artifact_hash,
                        attempt_number=existing_attempt.attempt_number,
                        attempt_recorded_at=existing_attempt.attempt_recorded_at,
                        must_start_by=existing_attempt.must_start_by,
                        claimant_id=claimant.actor_id,
                        persisted=True,
                        replayed=True,
                        reason="existing attempt returned (idempotent replay)",
                    )
                # Any actor field mismatch: CONFLICT.
                raise ExecutionAttemptConflictError(
                    f"claim {claim_id} already consumed by "
                    f"{existing_attempt.attempt_actor_id} "
                    f"(type={existing_attempt.attempt_actor_type}, "
                    f"ctx={existing_attempt.attempt_actor_context}); "
                    f"conflicting claimant {claimant.actor_id} "
                    f"(type={claimant.actor_type}, ctx={claimant.actor_context}) rejected"
                )

            # 2) Claim prerequisite.
            claim = self.get_claim(claim_id)
            if claim is None:
                raise ExecutionAttemptError(
                    f"attempt requires a persisted claim {claim_id}; no such claim"
                )
            if not claim.verify_hash():
                raise ExecutionAttemptError(
                    f"claim {claim_id} failed integrity verification"
                )

            # 3) Claim expiry: now must be <= claim_expires_at (inclusive boundary).
            claim_expires_dt = datetime.fromisoformat(
                claim.claim_expires_at.replace("Z", "+00:00")
            )
            if now_dt > claim_expires_dt:
                raise ExecutionAttemptClaimExpiredError(
                    f"claim {claim_id} expired at attempt-creation time; "
                    f"attempt blocked"
                )

            # 4) Authorization prerequisite.
            auth = self.get_authorization(authorization_id)
            if auth is None:
                raise ExecutionAttemptError(
                    f"attempt requires a persisted authorization "
                    f"{authorization_id}; no such authorization"
                )
            if not auth.verify_hash():
                raise ExecutionAttemptError(
                    f"authorization {authorization_id} failed integrity verification"
                )

            # 5) Lineage: claim must belong to this authorization.
            if claim.authorization_id != authorization_id:
                raise ExecutionAttemptLineageError(
                    f"claim {claim_id} belongs to authorization "
                    f"{claim.authorization_id}, not {authorization_id}"
                )
            if claim.authorization_hash != auth.artifact_hash:
                raise ExecutionAttemptLineageError(
                    f"authorization_hash mismatch for authorization "
                    f"{authorization_id}"
                )

            # 6) Attempt limit: derived from authorization scope (caller can't raise it).
            existing_attempts = self.get_attempts_for_authorization(authorization_id)
            current_count = len(existing_attempts)
            effective_limit = None
            if auth.authorized_scope is not None:
                effective_limit = auth.authorized_scope.attempt_limit
            if effective_limit is not None and current_count >= effective_limit:
                raise ExecutionAttemptLimitError(
                    f"authorization {authorization_id} has reached its attempt limit "
                    f"({effective_limit}); no more attempts allowed"
                )

            # 7) Next attempt number (monotonic).
            next_attempt_number = current_count + 1

            # 8) must_start_by: bounded by claim expiry.
            if must_start_within_seconds is not None:
                if must_start_within_seconds <= 0:
                    raise ExecutionAttemptError(
                        f"must_start_within_seconds must be positive, "
                        f"got {must_start_within_seconds}"
                    )
                must_start_dt = now_dt + timedelta(seconds=must_start_within_seconds)
                if must_start_dt > claim_expires_dt:
                    must_start_dt = claim_expires_dt
                must_start_by = must_start_dt.isoformat().replace("+00:00", "Z")
            else:
                must_start_by = claim.claim_expires_at

            # 9) Build the immutable Attempt.
            input_hash = (
                auth.authorized_scope.input_hash
                if auth.authorized_scope
                else secrets.token_hex(32)
            )
            operation = (
                auth.authorized_scope.operation
                if auth.authorized_scope
                else "run-sandboxed"
            )
            worker_class = (
                auth.authorized_scope.worker_class
                if auth.authorized_scope
                else "restricted-sandbox"
            )

            attempt = build_execution_attempt(
                authorization_id=authorization_id,
                authorization_hash=auth.artifact_hash,
                request_id=auth.request_id,
                request_hash=auth.request_hash,
                decision_id=auth.decision_id,
                decision_hash=auth.decision_hash,
                claim_id=claim.claim_id,
                claim_hash=claim.artifact_hash,
                task_id=auth.task_id,
                attempt_number=next_attempt_number,
                attempt_actor=claimant,
                attempt_requested_at=now,
                attempt_recorded_at=now,
                claim_expires_at=claim.claim_expires_at,
                must_start_by=must_start_by,
                input_hash=input_hash,
                operation=operation,
                worker_class=worker_class,
                status=ExecutionAttemptStatus.RECORDED,
            )

            # 10) Persist atomically (within this same transaction).
            # Use the transaction-neutral helper to avoid nested BEGIN.
            canonical = canonical_json(attempt.to_canonical_dict())
            payload_sha256 = sha256_text(canonical)
            linkage = _hash_attempt_linkage(
                attempt.attempt_id,
                attempt.authorization_id,
                attempt.authorization_hash,
                attempt.request_id,
                attempt.request_hash,
                attempt.decision_id,
                attempt.decision_hash,
                attempt.claim_id,
                attempt.claim_hash,
                attempt.task_id,
                attempt.attempt_number,
                attempt.attempt_actor_id,
                attempt.attempt_actor_type,
                attempt.attempt_actor_context,
                attempt.attempt_requested_at,
                attempt.attempt_recorded_at,
                attempt.claim_expires_at,
                attempt.must_start_by,
                attempt.input_hash,
                attempt.operation,
                attempt.worker_class,
                attempt.status.value,
            )
            self._insert_attempt_rows(attempt, canonical, payload_sha256, linkage)

            return ExecutionAttemptResult(
                authorization_id=authorization_id,
                claim_id=claim_id,
                attempt_id=attempt.attempt_id,
                attempt_hash=attempt.artifact_hash,
                attempt_number=attempt.attempt_number,
                attempt_recorded_at=attempt.attempt_recorded_at,
                must_start_by=attempt.must_start_by,
                claimant_id=claimant.actor_id,
                persisted=True,
                replayed=False,
                reason="ExecutionAttempt persisted",
            )

        try:
            return self._run_atomic(_work)
        except sqlite3.IntegrityError as exc:
            raise ExecutionAttemptConflictError(
                f"claim {claim_id} consumption conflict: {exc}"
            ) from exc

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
        # 1b) decision authorization-linkage envelope verification.
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
        # 1c) request-linkage envelope verification (decisions + authorizations).
        for table in (
            "execution_authorization_decisions",
            "execution_authorizations",
        ):
            for r in self._conn.execute(
                f"SELECT artifact_id, request_id, request_linkage_sha256 FROM {table}"
            ):
                try:
                    expected = _hash_request_linkage(r["artifact_id"], r["request_id"])
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        f"{table} {r['artifact_id']} request linkage unhashable: {exc}"
                    )
                    continue
                if expected != r["request_linkage_sha256"]:
                    failures.append(
                        f"{table} {r['artifact_id']} request linkage tamper detected"
                    )
        # 1d) physical request_id must equal the canonical artifact request_id.
        for table, attr in (
            ("execution_authorization_decisions", "decision"),
            ("execution_authorizations", "authorization"),
        ):
            for r in self._conn.execute(
                f"SELECT artifact_id, request_id, canonical_payload FROM {table}"
            ):
                try:
                    payload = json.loads(r["canonical_payload"])
                except Exception:  # noqa: BLE001
                    continue
                canonical_request_id = payload.get("request_id")
                if canonical_request_id != r["request_id"]:
                    failures.append(
                        f"{table} {r['artifact_id']} physical request_id "
                        f"({r['request_id']}) != canonical request_id "
                        f"({canonical_request_id})"
                    )
        # 1e) claim artifacts: hash re-verification + linkage tamper detection
        #     + one-claim-per-authorization + orphan detection.
        for r in self._conn.execute(
            "SELECT artifact_id, authorization_id, authorization_hash, request_id, "
            "request_hash, decision_id, decision_hash, artifact_hash, "
            "claim_linkage_sha256, canonical_payload FROM "
            "execution_authorization_claims"
        ):
            try:
                payload = json.loads(r["canonical_payload"])
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"execution_authorization_claims {r['artifact_id']} "
                    f"payload unparseable: {exc}"
                )
                continue
            if sha256_payload(payload) != r["artifact_hash"]:
                failures.append(
                    f"execution_authorization_claims {r['artifact_id']} "
                    f"artifact hash mismatch"
                )
            expected_linkage = _hash_claim_linkage(
                r["artifact_id"],
                r["authorization_id"],
                r["authorization_hash"],
                r["request_id"],
                r["request_hash"],
                r["decision_id"],
                r["decision_hash"],
            )
            if expected_linkage != r["claim_linkage_sha256"]:
                failures.append(
                    f"execution_authorization_claims {r['artifact_id']} "
                    f"claim linkage tamper detected"
                )
        # Multiple claims for one Authorization -> fail closed.
        for r in self._conn.execute(
            "SELECT authorization_id, COUNT(*) AS n FROM "
            "execution_authorization_claims GROUP BY authorization_id"
        ):
            if int(r["n"]) > 1:
                failures.append(
                    f"authorization {r['authorization_id']} has "
                    f"{r['n']} claims (at most one allowed)"
                )
        # Orphan claim: claim references a missing Authorization.
        for r in self._conn.execute(
            "SELECT artifact_id, authorization_id FROM "
            "execution_authorization_claims"
        ):
            auth = self._conn.execute(
                "SELECT 1 FROM execution_authorizations WHERE artifact_id = ?",
                (r["authorization_id"],),
            ).fetchone()
            if auth is None:
                failures.append(
                    f"claim {r['artifact_id']} references missing authorization "
                    f"{r['authorization_id']} (orphan claim)"
                )
        # 1f) attempt artifacts: hash re-verification + linkage tamper detection.
        for r in self._conn.execute(
            "SELECT artifact_id, authorization_id, authorization_hash, request_id, "
            "request_hash, decision_id, decision_hash, claim_id, claim_hash, "
            "attempt_number, attempt_actor_id, attempt_actor_type, "
            "attempt_actor_context, attempt_requested_at, attempt_recorded_at, "
            "claim_expires_at, must_start_by, input_hash, operation, "
            "worker_class, status, artifact_hash, attempt_linkage_sha256, "
            "canonical_payload FROM execution_attempts"
        ):
            try:
                payload = json.loads(r["canonical_payload"])
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"execution_attempts {r['artifact_id']} "
                    f"payload unparseable: {exc}"
                )
                continue
            if sha256_payload(payload) != r["artifact_hash"]:
                failures.append(
                    f"execution_attempts {r['artifact_id']} "
                    f"artifact hash mismatch"
                )
            expected_linkage = _hash_attempt_linkage(
                r["artifact_id"],
                r["authorization_id"],
                r["authorization_hash"],
                r["request_id"],
                r["request_hash"],
                r["decision_id"],
                r["decision_hash"],
                r["claim_id"],
                r["claim_hash"],
                r["task_id"],
                int(r["attempt_number"]),
                r["attempt_actor_id"],
                r["attempt_actor_type"],
                r["attempt_actor_context"],
                r["attempt_requested_at"],
                r["attempt_recorded_at"],
                r["claim_expires_at"],
                r["must_start_by"],
                r["input_hash"],
                r["operation"],
                r["worker_class"],
                r["status"],
            )
            if expected_linkage != r["attempt_linkage_sha256"]:
                failures.append(
                    f"execution_attempts {r['artifact_id']} "
                    f"attempt linkage tamper detected"
                )
            # Verify attempt_number is positive
            if int(r["attempt_number"]) < 1:
                failures.append(
                    f"execution_attempts {r['artifact_id']} "
                    f"invalid attempt_number {r['attempt_number']}"
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
        # 3) relational invariants: at most one terminal decision per request;
        # at most one authorization per request; no orphans.
        decisions = {
            r["request_id"]: r
            for r in self._conn.execute(
                "SELECT request_id, artifact_id, canonical_payload FROM "
                "execution_authorization_decisions"
            )
        }
        auths = {
            r["request_id"]: r
            for r in self._conn.execute(
                "SELECT request_id, artifact_id, canonical_payload FROM "
                "execution_authorizations"
            )
        }
        for req_id, d in decisions.items():
            if req_id in auths:
                # Must be a GRANTED decision paired with its authorization.
                try:
                    d_payload = json.loads(d["canonical_payload"])
                except Exception:  # noqa: BLE001
                    d_payload = {}
                if d_payload.get("outcome") != "GRANTED":
                    failures.append(
                        f"request {req_id} has an authorization but a "
                        f"non-GRANTED decision (orphan authorization)"
                    )
            else:
                try:
                    d_payload = json.loads(d["canonical_payload"])
                except Exception:  # noqa: BLE001
                    d_payload = {}
                if d_payload.get("outcome") == "GRANTED":
                    failures.append(
                        f"request {req_id} has a GRANTED decision with no "
                        f"matching authorization (orphan GRANTED decision)"
                    )
        for req_id, a in auths.items():
            if req_id not in decisions:
                failures.append(
                    f"request {req_id} has an authorization with no decision "
                    f"(orphan authorization)"
                )
        if failures:
            return IntegrityReport(ok=False, checked=len(rows), failures=tuple(failures))
        return IntegrityReport(ok=True, checked=len(rows))

    # -- lifecycle ----------------------------------------------------------
    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
