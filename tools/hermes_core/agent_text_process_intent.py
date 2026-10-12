"""Durable, non-executing intent for one accepted text receiver process."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.hashing import canonical_json, sha256_payload


_DDL = """CREATE TABLE IF NOT EXISTS agent_text_process_intents (
    attempt_id TEXT PRIMARY KEY,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_FIELDS = frozenset({
    "schema_version", "attempt_id", "delegation_id", "receiver_agent_id",
    "receipt_hash", "launch_attempt_hash", "start_result_hash",
    "bridge_hash", "task_input_hash", "idempotency_key", "runtime_run_id",
    "argv_hash", "reserved_at",
})
_TEXT_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class AgentTextProcessIntent:
    attempt_id: str
    receiver_agent_id: str
    bridge_hash: str
    argv_hash: str
    payload_sha256: str


class SQLiteAgentTextProcessIntentStore:
    def __init__(self, bridge_store: SQLiteAgentInvocationBridgeStore, *, clock=None):
        if type(bridge_store) is not SQLiteAgentInvocationBridgeStore:
            raise DelegationIntegrityError("text process intent bridge store denied")
        self.bridge_store = bridge_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        with closing(self._connect()) as conn:
            conn.execute(_DDL)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.bridge_store.authority.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @staticmethod
    def _read(conn, attempt_id: str) -> AgentTextProcessIntent | None:
        row = conn.execute(
            "SELECT canonical_payload,payload_sha256 FROM agent_text_process_intents "
            "WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("text process intent corrupt") from exc
        if (type(payload) is not dict or set(payload) != _FIELDS
                or canonical_json(payload) != row[0]
                or sha256_payload(payload) != row[1]
                or payload["schema_version"] != "ea4e92hp-text-process-intent-v1"
                or payload["attempt_id"] != attempt_id
                or payload["receiver_agent_id"] not in _TEXT_RECEIVERS
                or any(type(value) is not str or not value for value in payload.values())
                or any(not _HASH.fullmatch(payload[key]) for key in (
                    "receipt_hash", "launch_attempt_hash", "start_result_hash",
                    "bridge_hash", "task_input_hash", "argv_hash",
                ))):
            raise DelegationIntegrityError("text process intent integrity mismatch")
        try:
            _parse_timestamp(payload["reserved_at"])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("text process intent time invalid") from exc
        return AgentTextProcessIntent(
            attempt_id, payload["receiver_agent_id"], payload["bridge_hash"],
            payload["argv_hash"], row[1],
        )

    def get(self, attempt_id: str) -> AgentTextProcessIntent | None:
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("text process intent attempt missing")
        with closing(self._connect()) as conn:
            return self._read(conn, attempt_id)

    def reserve(self, attempt_id: str, argv: Sequence[str]) -> AgentTextProcessIntent:
        """Bind one command digest; this cannot start or authorize a process."""
        if (type(attempt_id) is not str or not attempt_id
                or type(argv) not in (tuple, list) or not argv
                or any(type(part) is not str or not part or "\x00" in part for part in argv)
                or sum(len(part.encode("utf-8")) for part in argv) > 65536):
            raise DelegationIntegrityError("text process intent command denied")
        witness = load_bound_agent_start(
            self.bridge_store.authority, self.bridge_store.start, attempt_id,
        )
        bridge = self.bridge_store.get(attempt_id)
        if (bridge is None or not bridge.verify_hash()
                or bridge.attempt_id != attempt_id
                or bridge.receipt_hash != witness.receipt.artifact_hash
                or bridge.launch_attempt_hash != witness.launch.artifact_hash
                or bridge.start_result_hash != witness.start_result.artifact_hash
                or bridge.receiver_agent_id != witness.receipt.receiver_agent_id):
            raise DelegationIntegrityError("text process intent bridge mismatch")
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise DelegationIntegrityError("text process intent clock invalid")
        now = now.astimezone(timezone.utc).replace(microsecond=0)
        if not (_parse_timestamp(witness.start_result.recorded_at) <= now
                < _parse_timestamp(witness.lease.expires_at)):
            raise DelegationIntegrityError("text process intent outside lease window")
        invocation = witness.bound.invocation
        payload = {
            "schema_version": "ea4e92hp-text-process-intent-v1",
            "attempt_id": attempt_id,
            "delegation_id": witness.task.delegation_id,
            "receiver_agent_id": witness.receipt.receiver_agent_id,
            "receipt_hash": witness.receipt.artifact_hash,
            "launch_attempt_hash": witness.launch.artifact_hash,
            "start_result_hash": witness.start_result.artifact_hash,
            "bridge_hash": bridge.artifact_hash,
            "task_input_hash": witness.task.task_input_hash,
            "idempotency_key": invocation.idempotency_key,
            "runtime_run_id": invocation.runtime_run_id,
            "argv_hash": sha256_payload(list(argv)),
            "reserved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        digest = sha256_payload(payload)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if self._read(conn, attempt_id) is not None:
                    raise DelegationIntegrityError("text process intent already reserved")
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
                stored_bridge = conn.execute(
                    "SELECT artifact_hash FROM agent_invocation_bridges WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()
                if (delegation != ("CREATED", witness.task.artifact_hash)
                        or lease != ("ACTIVE", witness.lease.artifact_hash)
                        or receipt != (witness.receipt.artifact_hash,)
                        or stored_bridge != (bridge.artifact_hash,)):
                    raise DelegationIntegrityError("text process intent authority changed")
                if conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='agent_receiver_start_fences'"
                ).fetchone() and conn.execute(
                    "SELECT 1 FROM agent_receiver_start_fences WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone():
                    raise DelegationIntegrityError("receiver start already claimed")
                for table, query in (
                    ("agent_terminal_captures",
                     "SELECT 1 FROM agent_terminal_captures WHERE attempt_id=?"),
                    ("delegation_results",
                     "SELECT 1 FROM delegation_results WHERE attempt_id=?"),
                ):
                    if conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,),
                    ).fetchone() and conn.execute(query, (attempt_id,)).fetchone():
                        raise DelegationIntegrityError("text process already terminal")
                conn.execute(
                    "INSERT INTO agent_text_process_intents VALUES(?,?,?)",
                    (attempt_id, canonical_json(payload), digest),
                )
                conn.commit()
                return AgentTextProcessIntent(
                    attempt_id, payload["receiver_agent_id"],
                    bridge.artifact_hash, payload["argv_hash"], digest,
                )
            except Exception:
                conn.rollback()
                raise
