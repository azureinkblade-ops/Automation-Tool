"""Immutable Kilo/OpenCode terminal capture for trusted-host crash recovery."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from tools.hermes_core.agent_result_candidate import (
    AgentResultCandidate, bind_terminal_agent_candidate,
    decode_agent_result_candidate,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.receiver_adapter import ExecutionOutcome, VerifiedResult
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


_DDL = """CREATE TABLE IF NOT EXISTS agent_terminal_captures (
    attempt_id TEXT PRIMARY KEY,
    capture_hash TEXT NOT NULL,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_TEXT_RECEIVERS = {"kilo-cli-agent": "completed", "opencode-cli-agent": "TERMINAL"}
_MAX_TEXT_BYTES = 65536
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class CapturedTerminalCandidate:
    capture_hash: str
    candidate: AgentResultCandidate
    captured_at: str


class SQLiteAgentTerminalCaptureStore:
    def __init__(self, authority: SQLiteDelegationStore, start: SQLiteExecutionStartStore,
                 *, clock=None):
        if type(authority) is not SQLiteDelegationStore or type(start) is not SQLiteExecutionStartStore:
            raise DelegationIntegrityError("terminal capture stores denied")
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

    def _read(self, conn, witness):
        row = conn.execute(
            "SELECT capture_hash,canonical_payload,payload_sha256 FROM agent_terminal_captures "
            "WHERE attempt_id=?", (witness.lease.attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[1])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("terminal capture payload corrupt") from exc
        if (canonical_json(payload) != row[1] or sha256_payload(payload) != row[0]
                or row[0] != row[2]):
            raise DelegationIntegrityError("terminal capture checksum mismatch")
        invocation = witness.bound.invocation
        expected = {
            "attempt_id": witness.lease.attempt_id,
            "start_result_hash": witness.start_result.artifact_hash,
            "receipt_hash": witness.receipt.artifact_hash,
            "idempotency_key": invocation.idempotency_key,
            "runtime_run_id": invocation.runtime_run_id,
            "receiver_agent_id": invocation.lineage.receiver_agent_id,
        }
        if (type(payload) is not dict or set(payload) != set(expected) | {
            "pid", "terminal_state", "argv_hash", "raw_text", "candidate_json",
            "captured_at",
        } or any(payload.get(key) != value for key, value in expected.items())
                or type(payload["pid"]) is not int or payload["pid"] <= 0
                or payload["terminal_state"] != _TEXT_RECEIVERS.get(expected["receiver_agent_id"])
                or type(payload["argv_hash"]) is not str
                or not _HASH.fullmatch(payload["argv_hash"])
                or type(payload["raw_text"]) is not str
                or len(payload["raw_text"].encode("utf-8")) > _MAX_TEXT_BYTES):
            raise DelegationIntegrityError("terminal capture lineage mismatch")
        try:
            captured_at = _parse_timestamp(payload["captured_at"])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("terminal capture time invalid") from exc
        if captured_at < _parse_timestamp(witness.start_result.recorded_at):
            raise DelegationIntegrityError("terminal capture predates durable start")
        candidate = decode_agent_result_candidate(
            invocation.lineage,
            VerifiedResult(valid=True, payload={"type": "text", "text": payload["raw_text"]}),
        )
        if candidate.candidate_json != payload["candidate_json"]:
            raise DelegationIntegrityError("terminal capture candidate mismatch")
        return CapturedTerminalCandidate(row[0], candidate, payload["captured_at"]), payload

    def get(self, attempt_id: str) -> CapturedTerminalCandidate | None:
        witness = load_bound_agent_start(self.authority, self.start, attempt_id)
        if witness.receipt.receiver_agent_id not in _TEXT_RECEIVERS:
            raise DelegationIntegrityError("terminal text receiver denied")
        with closing(self._connect()) as conn:
            row = self._read(conn, witness)
            return row[0] if row else None

    def capture(self, attempt_id: str, outcome: ExecutionOutcome) -> CapturedTerminalCandidate:
        witness = load_bound_agent_start(self.authority, self.start, attempt_id)
        invocation = witness.bound.invocation
        if invocation.lineage.receiver_agent_id not in _TEXT_RECEIVERS:
            raise DelegationIntegrityError("terminal text receiver denied")
        candidate = bind_terminal_agent_candidate(invocation, outcome)
        raw_text = outcome.verified_result.payload["text"]
        if len(raw_text.encode("utf-8")) > _MAX_TEXT_BYTES:
            raise DelegationIntegrityError("terminal text exceeds capture limit")
        payload = {
            "attempt_id": attempt_id,
            "start_result_hash": witness.start_result.artifact_hash,
            "receipt_hash": witness.receipt.artifact_hash,
            "idempotency_key": invocation.idempotency_key,
            "runtime_run_id": invocation.runtime_run_id,
            "receiver_agent_id": invocation.lineage.receiver_agent_id,
            "pid": outcome.record.pid,
            "terminal_state": outcome.record.terminal_state,
            "argv_hash": outcome.record.argv_hash,
            "raw_text": raw_text,
            "candidate_json": candidate.candidate_json,
        }
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._read(conn, witness)
                if existing is not None:
                    captured, stored = existing
                    if {key: value for key, value in stored.items() if key != "captured_at"} != payload:
                        raise DelegationIntegrityError("divergent terminal capture replay")
                    conn.rollback()
                    return captured
                status = conn.execute(
                    "SELECT status FROM delegations WHERE delegation_id=?",
                    (witness.task.delegation_id,),
                ).fetchone()
                lease_status = conn.execute(
                    "SELECT status FROM capability_leases WHERE lease_id=?",
                    (witness.lease.lease_id,),
                ).fetchone()
                if status != ("CREATED",) or lease_status != ("ACTIVE",):
                    raise DelegationIntegrityError("inactive terminal capture authority")
                now = self._clock()
                if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
                    raise DelegationIntegrityError("trusted terminal clock must be timezone-aware")
                now = now.astimezone(timezone.utc).replace(microsecond=0)
                if not _parse_timestamp(witness.start_result.recorded_at) <= now < _parse_timestamp(witness.lease.expires_at):
                    raise DelegationIntegrityError("terminal capture outside durable start or lease")
                payload["captured_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                digest = sha256_payload(payload)
                conn.execute(
                    "INSERT INTO agent_terminal_captures VALUES(?,?,?,?)",
                    (attempt_id, digest, canonical_json(payload), digest),
                )
                conn.commit()
                return CapturedTerminalCandidate(digest, candidate, payload["captured_at"])
            except Exception:
                conn.rollback()
                raise
