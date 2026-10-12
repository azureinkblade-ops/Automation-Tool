"""One-shot durable fence before a delegated text receiver process may start.

This store does not grant invocation authority or start a process. An existing
claim is evidence that start may have been attempted and must never be retried
by merely replaying the request.
"""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


_DDL = """CREATE TABLE IF NOT EXISTS agent_receiver_start_fences (
    attempt_id TEXT PRIMARY KEY,
    claim_hash TEXT NOT NULL,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_TEXT_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema_version",
    "attempt_id", "delegation_id", "receipt_hash", "launch_attempt_hash",
    "start_result_hash", "receiver_agent_id", "idempotency_key",
    "runtime_run_id", "claimed_at",
})


@dataclass(frozen=True)
class AgentReceiverStartFence:
    attempt_id: str
    claim_hash: str
    receiver_agent_id: str
    receipt_hash: str
    launch_attempt_hash: str
    start_result_hash: str
    idempotency_key: str
    runtime_run_id: str
    claimed_at: str


class SQLiteAgentReceiverStartFenceStore:
    def __init__(self, authority: SQLiteDelegationStore,
                 start: SQLiteExecutionStartStore, *, clock=None):
        if type(authority) is not SQLiteDelegationStore or type(start) is not SQLiteExecutionStartStore:
            raise DelegationIntegrityError("receiver start fence stores denied")
        self.authority = authority
        self.start = start
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        with closing(self._connect()) as conn:
            conn.execute(_DDL)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.authority.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _read(conn, attempt_id: str) -> AgentReceiverStartFence | None:
        row = conn.execute(
            "SELECT claim_hash,canonical_payload,payload_sha256 "
            "FROM agent_receiver_start_fences WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[1])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("receiver start fence corrupt") from exc
        if (type(payload) is not dict or set(payload) != _FIELDS
                or canonical_json(payload) != row[1]
                or sha256_payload(payload) != row[0] or row[0] != row[2]
                or payload["schema_version"] != "1"
                or payload["attempt_id"] != attempt_id
                or any(type(payload[key]) is not str or not payload[key]
                       for key in _FIELDS)
                or any(not _HASH.fullmatch(payload[key]) for key in (
                    "receipt_hash", "launch_attempt_hash", "start_result_hash",
                ))
                or payload["receiver_agent_id"] not in _TEXT_RECEIVERS):
            raise DelegationIntegrityError("receiver start fence integrity mismatch")
        try:
            _parse_timestamp(payload["claimed_at"])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("receiver start fence time invalid") from exc
        return AgentReceiverStartFence(
            attempt_id, row[0], payload["receiver_agent_id"],
            payload["receipt_hash"], payload["launch_attempt_hash"],
            payload["start_result_hash"], payload["idempotency_key"],
            payload["runtime_run_id"], payload["claimed_at"],
        )

    def get(self, attempt_id: str) -> AgentReceiverStartFence | None:
        """Inspect historical start ambiguity; this never grants a new start."""
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("receiver start attempt identity missing")
        with closing(self._connect()) as conn:
            return self._read(conn, attempt_id)

    def claim(self, attempt_id: str) -> AgentReceiverStartFence:
        """Record one irreversible intent; duplicate calls deny rather than replay."""
        witness = load_bound_agent_start(self.authority, self.start, attempt_id)
        invocation = witness.bound.invocation
        receiver = invocation.lineage.receiver_agent_id
        if receiver not in _TEXT_RECEIVERS:
            raise DelegationIntegrityError("receiver start fence is for text agents only")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if self._read(conn, attempt_id) is not None:
                    raise DelegationIntegrityError("receiver start already claimed; reconcile only")
                delegation = conn.execute(
                    "SELECT status,artifact_hash FROM delegations WHERE delegation_id=?",
                    (witness.task.delegation_id,),
                ).fetchone()
                lease = conn.execute(
                    "SELECT status,artifact_hash FROM capability_leases WHERE lease_id=?",
                    (witness.lease.lease_id,),
                ).fetchone()
                receipt = conn.execute(
                    "SELECT artifact_hash FROM delegation_receipts WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()
                if (delegation != ("CREATED", witness.task.artifact_hash)
                        or lease != ("ACTIVE", witness.lease.artifact_hash)
                        or receipt != (witness.receipt.artifact_hash,)):
                    raise DelegationIntegrityError("receiver start authority changed")
                terminal_tables = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name IN ('agent_terminal_captures','delegation_results')"
                    )
                }
                terminal_queries = {
                    "agent_terminal_captures":
                        "SELECT 1 FROM agent_terminal_captures WHERE attempt_id=?",
                    "delegation_results":
                        "SELECT 1 FROM delegation_results WHERE attempt_id=?",
                }
                for table in terminal_tables:
                    if conn.execute(
                        terminal_queries[table], (attempt_id,),
                    ).fetchone() is not None:
                        raise DelegationIntegrityError(
                            "receiver terminal state already recorded; reconcile only"
                        )
                now = self._clock()
                if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
                    raise DelegationIntegrityError("receiver start clock must be timezone-aware")
                now = now.astimezone(timezone.utc).replace(microsecond=0)
                if not (_parse_timestamp(witness.start_result.recorded_at) <= now
                        < _parse_timestamp(witness.lease.expires_at)):
                    raise DelegationIntegrityError("receiver start outside lease window")
                payload = {
                    "schema_version": "1",
                    "attempt_id": attempt_id,
                    "delegation_id": witness.task.delegation_id,
                    "receipt_hash": witness.receipt.artifact_hash,
                    "launch_attempt_hash": witness.launch.artifact_hash,
                    "start_result_hash": witness.start_result.artifact_hash,
                    "receiver_agent_id": receiver,
                    "idempotency_key": invocation.idempotency_key,
                    "runtime_run_id": invocation.runtime_run_id,
                    "claimed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                digest = sha256_payload(payload)
                conn.execute(
                    "INSERT INTO agent_receiver_start_fences VALUES(?,?,?,?)",
                    (attempt_id, digest, canonical_json(payload), digest),
                )
                conn.commit()
                return AgentReceiverStartFence(
                    attempt_id, digest, receiver, witness.receipt.artifact_hash,
                    witness.launch.artifact_hash, witness.start_result.artifact_hash,
                    invocation.idempotency_key, invocation.runtime_run_id,
                    payload["claimed_at"],
                )
            except Exception:
                conn.rollback()
                raise
