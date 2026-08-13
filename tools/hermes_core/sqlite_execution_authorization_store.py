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
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .execution_authorization import (
    ExecutionAuthorization,
    ExecutionAuthorizationDecision,
    ExecutionAuthorizationDecisionOutcome,
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
    ExecutionAuthorizationStoreError,
    ExecutionAuthorityLedgerEntry,
    IntegrityReport,
)
from .hashing import canonical_json, sha256_payload, sha256_text

SCHEMA_VERSION = 3
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
        # Test-only failure-injection seam: when set, the atomic grant method
        # raises immediately after the decision row + its ledger event are
        # written but before the authorization is persisted (to prove rollback
        # leaves zero residue). Never exposed as public API.
        self._fail_after_decision = False
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

    def _request_id_for(self, artifact: Any) -> Optional[str]:
        if isinstance(artifact, ExecutionAuthorizationRequest):
            return None  # request_id IS the artifact_id for requests
        return getattr(artifact, "request_id", None)

    def _run_atomic(self, fn) -> None:
        """Own a single SQLite transaction around fn (no nested commits)."""
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            fn()
            self._conn.commit()
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
