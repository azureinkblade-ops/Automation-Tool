"""Durable reported process facts; no process launch or provenance attestation."""

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import re

from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.hashing import canonical_json, sha256_payload


_START_DDL = """CREATE TABLE IF NOT EXISTS agent_text_process_starts (
    attempt_id TEXT PRIMARY KEY,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_TERMINAL_DDL = """CREATE TABLE IF NOT EXISTS agent_text_process_terminals (
    attempt_id TEXT PRIMARY KEY,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    stdout_bytes BLOB NOT NULL,
    stderr_bytes BLOB NOT NULL
);"""
_MAX_STDOUT = 4 * 1024 * 1024
_MAX_STDERR = 128 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ReportedTextProcessStart:
    attempt_id: str
    start_hash: str
    intent_hash: str
    fence_hash: str
    owner_id: str
    pid: int
    argv_hash: str
    started_at: str


@dataclass(frozen=True)
class ReportedTextProcessTerminal:
    attempt_id: str
    terminal_hash: str
    start_hash: str
    owner_id: str
    pid: int
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes
    recorded_at: str


class SQLiteAgentTextProcessObservationStore:
    def __init__(self, intents: SQLiteAgentTextProcessIntentStore,
                 fences: SQLiteAgentReceiverStartFenceStore, *, clock=None):
        if (type(intents) is not SQLiteAgentTextProcessIntentStore
                or type(fences) is not SQLiteAgentReceiverStartFenceStore
                or intents.bridge_store.authority is not fences.authority
                or intents.bridge_store.start is not fences.start):
            raise DelegationIntegrityError("text process observation stores denied")
        self.intents = intents
        self.fences = fences
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        with closing(self._connect()) as conn:
            conn.execute(_START_DDL)
            conn.execute(_TERMINAL_DDL)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.intents.bridge_store.authority.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _now(self):
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise DelegationIntegrityError("text process observation clock invalid")
        return now.astimezone(timezone.utc).replace(microsecond=0)

    @staticmethod
    def _read_start(conn, attempt_id):
        row = conn.execute(
            "SELECT canonical_payload,payload_sha256 FROM agent_text_process_starts "
            "WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("text process start corrupt") from exc
        if (type(payload) is not dict or set(payload) != {
                "schema_version", "attempt_id", "intent_hash", "fence_hash",
                "owner_id", "pid", "argv_hash", "started_at",
        } or payload["schema_version"] != "ea4e92hv-text-process-start-v1"
                or payload["attempt_id"] != attempt_id
                or type(payload["pid"]) is not int or payload["pid"] <= 0
                or any(type(payload[key]) is not str or not payload[key]
                       for key in ("intent_hash", "fence_hash", "owner_id", "argv_hash"))
                or any(not _HASH.fullmatch(payload[key]) for key in (
                    "intent_hash", "fence_hash", "argv_hash",
                ))
                or canonical_json(payload) != row[0]
                or sha256_payload(payload) != row[1]):
            raise DelegationIntegrityError("text process start integrity mismatch")
        try:
            _parse_timestamp(payload["started_at"])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("text process start time invalid") from exc
        return ReportedTextProcessStart(
            attempt_id, row[1], payload["intent_hash"], payload["fence_hash"],
            payload["owner_id"], payload["pid"], payload["argv_hash"],
            payload["started_at"],
        )

    @staticmethod
    def _read_terminal(conn, attempt_id):
        row = conn.execute(
            "SELECT canonical_payload,payload_sha256,stdout_bytes,stderr_bytes "
            "FROM agent_text_process_terminals WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        start = SQLiteAgentTextProcessObservationStore._read_start(conn, attempt_id)
        try:
            payload = json.loads(row[0])
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("text process terminal corrupt") from exc
        stdout, stderr = row[2], row[3]
        if (start is None or type(payload) is not dict or set(payload) != {
                "schema_version", "attempt_id", "start_hash", "owner_id", "pid",
                "returncode", "stdout_sha256", "stderr_sha256", "recorded_at",
        } or payload["schema_version"] != "ea4e92hv-text-process-terminal-v1"
                or payload["attempt_id"] != attempt_id
                or payload["start_hash"] != start.start_hash
                or payload["owner_id"] != start.owner_id or payload["pid"] != start.pid
                or type(payload["returncode"]) is not int
                or type(stdout) is not bytes or type(stderr) is not bytes
                or len(stdout) > _MAX_STDOUT or len(stderr) > _MAX_STDERR
                or payload["stdout_sha256"] != hashlib.sha256(stdout).hexdigest()
                or payload["stderr_sha256"] != hashlib.sha256(stderr).hexdigest()
                or canonical_json(payload) != row[0]
                or sha256_payload(payload) != row[1]):
            raise DelegationIntegrityError("text process terminal integrity mismatch")
        try:
            if _parse_timestamp(payload["recorded_at"]) < _parse_timestamp(start.started_at):
                raise DelegationIntegrityError("text process terminal predates start")
        except (TypeError, ValueError) as exc:
            raise DelegationIntegrityError("text process terminal time invalid") from exc
        return ReportedTextProcessTerminal(
            attempt_id, row[1], start.start_hash, start.owner_id, start.pid,
            payload["returncode"], stdout, stderr, payload["recorded_at"],
        )

    def get_start(self, attempt_id: str) -> ReportedTextProcessStart | None:
        with closing(self._connect()) as conn:
            return self._read_start(conn, attempt_id)

    def get_terminal(self, attempt_id: str) -> ReportedTextProcessTerminal | None:
        with closing(self._connect()) as conn:
            return self._read_terminal(conn, attempt_id)

    def record_start(self, attempt_id: str, argv: tuple[str, ...], *,
                     owner_id: str, pid: int) -> ReportedTextProcessStart:
        """Account a reported start after fencing; not a process permit."""
        if (type(owner_id) is not str or not owner_id or len(owner_id) > 128
                or "\x00" in owner_id or type(pid) is not int or pid <= 0):
            raise DelegationIntegrityError("text process start identity denied")
        intent = self.intents.verify_command(attempt_id, argv)
        fence = self.fences.get(attempt_id)
        bridge = self.intents.bridge_store.get(attempt_id)
        witness = load_bound_agent_start(
            self.intents.bridge_store.authority, self.intents.bridge_store.start,
            attempt_id,
        )
        if (fence is None or bridge is None
                or fence.receiver_agent_id != intent.receiver_agent_id
                or fence.receipt_hash != witness.receipt.artifact_hash
                or fence.start_result_hash != witness.start_result.artifact_hash):
            raise DelegationIntegrityError("text process start fence mismatch")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if self._read_start(conn, attempt_id) is not None:
                    raise DelegationIntegrityError("text process start already recorded")
                current_intent = SQLiteAgentTextProcessIntentStore._read(conn, attempt_id)
                current_fence = SQLiteAgentReceiverStartFenceStore._read(conn, attempt_id)
                claim = conn.execute(
                    "SELECT execution_request_id FROM agent_invocation_claim_intents "
                    "WHERE attempt_id=?", (attempt_id,),
                ).fetchone() if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='agent_invocation_claim_intents'"
                ).fetchone() else None
                status = conn.execute(
                    "SELECT status,artifact_hash FROM delegations WHERE delegation_id=?",
                    (witness.task.delegation_id,),
                ).fetchone()
                lease = conn.execute(
                    "SELECT status,artifact_hash FROM capability_leases WHERE lease_id=?",
                    (witness.lease.lease_id,),
                ).fetchone()
                if (current_intent != intent or current_fence != fence
                        or claim != (bridge.execution_request_id,)
                        or status != ("CREATED", witness.task.artifact_hash)
                        or lease != ("ACTIVE", witness.lease.artifact_hash)):
                    raise DelegationIntegrityError("text process start authority changed")
                now = self._now()
                if not (_parse_timestamp(fence.claimed_at) <= now
                        < _parse_timestamp(witness.lease.expires_at)):
                    raise DelegationIntegrityError("text process start outside lease")
                payload = {
                    "schema_version": "ea4e92hv-text-process-start-v1",
                    "attempt_id": attempt_id, "intent_hash": intent.payload_sha256,
                    "fence_hash": fence.claim_hash, "owner_id": owner_id,
                    "pid": pid, "argv_hash": intent.argv_hash,
                    "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                digest = sha256_payload(payload)
                conn.execute(
                    "INSERT INTO agent_text_process_starts VALUES(?,?,?)",
                    (attempt_id, canonical_json(payload), digest),
                )
                conn.commit()
                return self._read_start(conn, attempt_id)
            except Exception:
                conn.rollback()
                raise

    def record_terminal(self, attempt_id: str, *, owner_id: str, pid: int,
                        returncode: int, stdout_bytes: bytes,
                        stderr_bytes: bytes) -> ReportedTextProcessTerminal:
        """Retain bounded reported bytes, including after cancellation/expiry."""
        if (type(owner_id) is not str or type(pid) is not int
                or type(returncode) is not int
                or type(stdout_bytes) is not bytes or type(stderr_bytes) is not bytes
                or len(stdout_bytes) > _MAX_STDOUT or len(stderr_bytes) > _MAX_STDERR):
            raise DelegationIntegrityError("text process terminal data denied")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                start = self._read_start(conn, attempt_id)
                if start is None or start.owner_id != owner_id or start.pid != pid:
                    raise DelegationIntegrityError("text process terminal owner mismatch")
                existing = self._read_terminal(conn, attempt_id)
                if existing is not None:
                    if (existing.returncode != returncode
                            or existing.stdout_bytes != stdout_bytes
                            or existing.stderr_bytes != stderr_bytes):
                        raise DelegationIntegrityError("divergent text process terminal")
                    conn.rollback()
                    return existing
                now = self._now()
                if now < _parse_timestamp(start.started_at):
                    raise DelegationIntegrityError("text process terminal predates start")
                payload = {
                    "schema_version": "ea4e92hv-text-process-terminal-v1",
                    "attempt_id": attempt_id, "start_hash": start.start_hash,
                    "owner_id": owner_id, "pid": pid, "returncode": returncode,
                    "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
                    "recorded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                digest = sha256_payload(payload)
                conn.execute(
                    "INSERT INTO agent_text_process_terminals VALUES(?,?,?,?,?)",
                    (attempt_id, canonical_json(payload), digest,
                     stdout_bytes, stderr_bytes),
                )
                conn.commit()
                return self._read_terminal(conn, attempt_id)
            except Exception:
                conn.rollback()
                raise
