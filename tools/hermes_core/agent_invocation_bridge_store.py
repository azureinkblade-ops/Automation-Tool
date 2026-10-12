"""Durable identity reservation for an accepted text-agent invocation.

This store cannot issue authorization or execute a receiver. A persisted bridge
is historical lineage only; cancellation and expiry still revoke use.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from tools.hermes_core.agent_invocation_bridge import (
    AgentInvocationBridge, bind_agent_invocation_request,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.governed_bound_executor import GovernedExecutorResolution
from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


_DDL = """CREATE TABLE IF NOT EXISTS agent_invocation_bridges (
    attempt_id TEXT PRIMARY KEY,
    execution_request_id TEXT NOT NULL UNIQUE,
    artifact_hash TEXT NOT NULL,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_SCHEMA = "ea4e92he-agent-invocation-bridge-v1"
_FIELDS = frozenset(AgentInvocationBridge.__dataclass_fields__) - {"artifact_hash"}


class SQLiteAgentInvocationBridgeStore:
    def __init__(self, authority: SQLiteDelegationStore,
                 start: SQLiteExecutionStartStore, *, clock=None):
        if type(authority) is not SQLiteDelegationStore or type(start) is not SQLiteExecutionStartStore:
            raise DelegationIntegrityError("invocation bridge stores denied")
        self.authority = authority
        self.start = start
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        with closing(self._connect()) as conn:
            conn.execute(_DDL)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.authority.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @staticmethod
    def _read(conn, attempt_id: str) -> AgentInvocationBridge | None:
        row = conn.execute(
            "SELECT execution_request_id,artifact_hash,canonical_payload,payload_sha256 "
            "FROM agent_invocation_bridges WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[2])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("invocation bridge payload corrupt") from exc
        if (type(payload) is not dict or set(payload) != _FIELDS | {"schema_version"}
                or payload.get("schema_version") != _SCHEMA
                or any(type(payload[key]) is not str or not payload[key]
                       for key in _FIELDS)
                or payload["attempt_id"] != attempt_id
                or payload["execution_request_id"] != row[0]
                or canonical_json(payload) != row[2]
                or sha256_payload(payload) != row[1] or row[1] != row[3]):
            raise DelegationIntegrityError("invocation bridge integrity mismatch")
        bridge = AgentInvocationBridge(
            **{key: payload[key] for key in _FIELDS}, artifact_hash=row[1],
        )
        if not bridge.verify_hash():
            raise DelegationIntegrityError("invocation bridge hash mismatch")
        return bridge

    def get(self, attempt_id: str) -> AgentInvocationBridge | None:
        """Read historical lineage, including after revocation; grants no use."""
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("invocation bridge attempt missing")
        with closing(self._connect()) as conn:
            return self._read(conn, attempt_id)

    def reserve(self, attempt_id: str,
                resolution: GovernedExecutorResolution) -> AgentInvocationBridge:
        """Persist exact identity once; exact active replay returns the same row."""
        witness = load_bound_agent_start(self.authority, self.start, attempt_id)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                status = conn.execute(
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
                if (status != ("CREATED", witness.task.artifact_hash)
                        or lease != ("ACTIVE", witness.lease.artifact_hash)
                        or receipt != (witness.receipt.artifact_hash,)):
                    raise DelegationIntegrityError("invocation bridge authority changed")
                if conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='agent_receiver_start_fences'"
                ).fetchone() and conn.execute(
                    "SELECT 1 FROM agent_receiver_start_fences WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone():
                    raise DelegationIntegrityError("receiver start already claimed")
                terminal_tables = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name IN ('agent_terminal_captures','delegation_results')"
                    )
                }
                for table in terminal_tables:
                    query = {
                        "agent_terminal_captures":
                            "SELECT 1 FROM agent_terminal_captures WHERE attempt_id=?",
                        "delegation_results":
                            "SELECT 1 FROM delegation_results WHERE attempt_id=?",
                    }[table]
                    if conn.execute(query, (attempt_id,)).fetchone() is not None:
                        raise DelegationIntegrityError("agent terminal state already recorded")
                now = self._clock()
                if (type(now) is not datetime or now.tzinfo is None
                        or now.utcoffset() is None):
                    raise DelegationIntegrityError("invocation bridge clock invalid")
                bridge = bind_agent_invocation_request(
                    witness, resolution, now=now,
                )
                existing = self._read(conn, attempt_id)
                if existing is not None:
                    if existing != bridge:
                        raise DelegationIntegrityError("divergent invocation bridge replay")
                    conn.rollback()
                    return existing
                payload = bridge.to_canonical_dict()
                conn.execute(
                    "INSERT INTO agent_invocation_bridges VALUES(?,?,?,?,?)",
                    (attempt_id, bridge.execution_request_id, bridge.artifact_hash,
                     canonical_json(payload), bridge.artifact_hash),
                )
                conn.commit()
                return bridge
            except Exception:
                conn.rollback()
                raise
