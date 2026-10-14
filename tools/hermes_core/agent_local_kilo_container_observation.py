"""Durable, caller-reported Kilo container facts; never start Docker."""

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.hashing import canonical_json, sha256_payload


_START_DDL = """CREATE TABLE IF NOT EXISTS agent_local_kilo_container_starts (
    attempt_id TEXT PRIMARY KEY,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_TERMINAL_DDL = """CREATE TABLE IF NOT EXISTS agent_local_kilo_container_terminals (
    attempt_id TEXT PRIMARY KEY,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    stdout_bytes BLOB NOT NULL,
    stderr_bytes BLOB NOT NULL
);"""
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MAX_STDOUT = 4 * 1024 * 1024
_MAX_STDERR = 128 * 1024


@dataclass(frozen=True)
class ReportedKiloContainerStart:
    attempt_id: str
    start_hash: str
    created_hash: str
    fence_hash: str
    container_id: str
    network_id: str
    owner_id: str
    started_at: str


@dataclass(frozen=True)
class ReportedKiloContainerTerminal:
    attempt_id: str
    terminal_hash: str
    start_hash: str
    exit_code: int
    stdout_bytes: bytes
    stderr_bytes: bytes
    recorded_at: str


class SQLiteAgentLocalKiloContainerObservationStore:
    """Account reports only; daemon identity and byte provenance remain unproven."""

    def __init__(self, created: SQLiteAgentLocalKiloContainerRecordStore,
                 fences: SQLiteAgentReceiverStartFenceStore, *, clock=None):
        if (type(created) is not SQLiteAgentLocalKiloContainerRecordStore
                or type(fences) is not SQLiteAgentReceiverStartFenceStore
                or created.intents.bridge_store.authority is not fences.authority
                or created.intents.bridge_store.start is not fences.start):
            raise DelegationIntegrityError("Kilo container observation stores denied")
        self.created = created
        self.fences = fences
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        with closing(self._connect()) as conn:
            conn.execute(_START_DDL)
            conn.execute(_TERMINAL_DDL)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.fences.authority.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _now(self):
        value = self._clock()
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise DelegationIntegrityError("Kilo container observation clock invalid")
        return value.astimezone(timezone.utc).replace(microsecond=0)

    @staticmethod
    def _read_start(conn, attempt_id):
        row = conn.execute(
            "SELECT canonical_payload,payload_sha256 FROM agent_local_kilo_container_starts "
            "WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
            created = SQLiteAgentLocalKiloContainerRecordStore._read(conn, attempt_id)
            fence = SQLiteAgentReceiverStartFenceStore._read(conn, attempt_id)
            if (type(payload) is not dict or set(payload) != {
                    "schema_id", "attempt_id", "created_hash", "fence_hash",
                    "container_id", "network_id", "owner_id", "started_at",
            } or payload["schema_id"] != "hermes.agent-local-kilo-container-start/v1"
                    or payload["attempt_id"] != attempt_id
                    or created is None or fence is None
                    or payload["created_hash"] != created.payload_sha256
                    or payload["fence_hash"] != fence.claim_hash
                    or payload["container_id"] != created.container_id
                    or payload["network_id"] != created.network_id
                    or type(payload["owner_id"]) is not str
                    or not payload["owner_id"] or len(payload["owner_id"]) > 128
                    or "\x00" in payload["owner_id"]
                    or any(not _HASH.fullmatch(payload[key]) for key in (
                        "created_hash", "fence_hash", "container_id", "network_id",
                    ))
                    or _parse_timestamp(payload["started_at"])
                    < _parse_timestamp(fence.claimed_at)
                    or canonical_json(payload) != row[0]
                    or sha256_payload(payload) != row[1]):
                raise DelegationIntegrityError("Kilo container start integrity mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise DelegationIntegrityError("Kilo container start integrity mismatch") from exc
        return ReportedKiloContainerStart(
            attempt_id, row[1], created.payload_sha256, fence.claim_hash,
            created.container_id, created.network_id, payload["owner_id"],
            payload["started_at"],
        )

    @staticmethod
    def _read_terminal(conn, attempt_id):
        row = conn.execute(
            "SELECT canonical_payload,payload_sha256,stdout_bytes,stderr_bytes "
            "FROM agent_local_kilo_container_terminals WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        start = SQLiteAgentLocalKiloContainerObservationStore._read_start(conn, attempt_id)
        try:
            payload = json.loads(row[0])
            stdout, stderr = row[2], row[3]
            if (start is None or type(payload) is not dict or set(payload) != {
                    "schema_id", "attempt_id", "start_hash", "exit_code",
                    "stdout_sha256", "stderr_sha256", "recorded_at",
            } or payload["schema_id"] != "hermes.agent-local-kilo-container-terminal/v1"
                    or payload["attempt_id"] != attempt_id
                    or payload["start_hash"] != start.start_hash
                    or type(payload["exit_code"]) is not int
                    or type(stdout) is not bytes or type(stderr) is not bytes
                    or len(stdout) > _MAX_STDOUT or len(stderr) > _MAX_STDERR
                    or payload["stdout_sha256"] != hashlib.sha256(stdout).hexdigest()
                    or payload["stderr_sha256"] != hashlib.sha256(stderr).hexdigest()
                    or _parse_timestamp(payload["recorded_at"])
                    < _parse_timestamp(start.started_at)
                    or canonical_json(payload) != row[0]
                    or sha256_payload(payload) != row[1]):
                raise DelegationIntegrityError("Kilo container terminal integrity mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise DelegationIntegrityError("Kilo container terminal integrity mismatch") from exc
        return ReportedKiloContainerTerminal(
            attempt_id, row[1], start.start_hash, payload["exit_code"],
            stdout, stderr, payload["recorded_at"],
        )

    def get_start(self, attempt_id):
        with closing(self._connect()) as conn:
            return self._read_start(conn, attempt_id)

    def get_terminal(self, attempt_id):
        with closing(self._connect()) as conn:
            return self._read_terminal(conn, attempt_id)

    def record_start(self, attempt_id: str, *, container_id: str,
                     network_id: str, owner_id: str) -> ReportedKiloContainerStart:
        if (type(owner_id) is not str or not owner_id or len(owner_id) > 128
                or "\x00" in owner_id or type(container_id) is not str
                or type(network_id) is not str):
            raise DelegationIntegrityError("Kilo container start identity denied")
        witness = load_bound_agent_start(
            self.fences.authority, self.fences.start, attempt_id,
        )
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if self._read_start(conn, attempt_id) is not None:
                    raise DelegationIntegrityError("Kilo container start already recorded")
                created = SQLiteAgentLocalKiloContainerRecordStore._read(conn, attempt_id)
                fence = SQLiteAgentReceiverStartFenceStore._read(conn, attempt_id)
                claim = conn.execute(
                    "SELECT execution_request_id FROM agent_invocation_claim_intents "
                    "WHERE attempt_id=?", (attempt_id,),
                ).fetchone() if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='agent_invocation_claim_intents'"
                ).fetchone() else None
                bridge = self.created.intents.bridge_store.get(attempt_id)
                status = conn.execute(
                    "SELECT status,artifact_hash FROM delegations WHERE delegation_id=?",
                    (witness.task.delegation_id,),
                ).fetchone()
                lease = conn.execute(
                    "SELECT status,artifact_hash FROM capability_leases WHERE lease_id=?",
                    (witness.lease.lease_id,),
                ).fetchone()
                if (created is None or fence is None or bridge is None
                        or container_id != created.container_id
                        or network_id != created.network_id
                        or fence.receiver_agent_id != "kilo-cli-agent"
                        or fence.receipt_hash != witness.receipt.artifact_hash
                        or fence.start_result_hash != witness.start_result.artifact_hash
                        or claim != (bridge.execution_request_id,)
                        or status != ("CREATED", witness.task.artifact_hash)
                        or lease != ("ACTIVE", witness.lease.artifact_hash)):
                    raise DelegationIntegrityError("Kilo container start authority mismatch")
                now = self._now()
                if not (_parse_timestamp(fence.claimed_at) <= now
                        < _parse_timestamp(witness.lease.expires_at)):
                    raise DelegationIntegrityError("Kilo container start outside lease")
                payload = {
                    "schema_id": "hermes.agent-local-kilo-container-start/v1",
                    "attempt_id": attempt_id, "created_hash": created.payload_sha256,
                    "fence_hash": fence.claim_hash, "container_id": container_id,
                    "network_id": network_id, "owner_id": owner_id,
                    "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                conn.execute(
                    "INSERT INTO agent_local_kilo_container_starts VALUES(?,?,?)",
                    (attempt_id, canonical_json(payload), sha256_payload(payload)),
                )
                conn.commit()
                return self._read_start(conn, attempt_id)
            except Exception:
                conn.rollback()
                raise

    def record_terminal(self, attempt_id: str, *, container_id: str,
                        owner_id: str, exit_code: int, stdout_bytes: bytes,
                        stderr_bytes: bytes) -> ReportedKiloContainerTerminal:
        if (type(container_id) is not str or type(owner_id) is not str
                or type(exit_code) is not int or type(stdout_bytes) is not bytes
                or type(stderr_bytes) is not bytes or len(stdout_bytes) > _MAX_STDOUT
                or len(stderr_bytes) > _MAX_STDERR):
            raise DelegationIntegrityError("Kilo container terminal data denied")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                start = self._read_start(conn, attempt_id)
                if (start is None or start.container_id != container_id
                        or start.owner_id != owner_id):
                    raise DelegationIntegrityError("Kilo container terminal owner mismatch")
                existing = self._read_terminal(conn, attempt_id)
                if existing is not None:
                    if (existing.exit_code != exit_code
                            or existing.stdout_bytes != stdout_bytes
                            or existing.stderr_bytes != stderr_bytes):
                        raise DelegationIntegrityError("divergent Kilo container terminal")
                    conn.rollback()
                    return existing
                now = self._now()
                if now < _parse_timestamp(start.started_at):
                    raise DelegationIntegrityError("Kilo container terminal predates start")
                payload = {
                    "schema_id": "hermes.agent-local-kilo-container-terminal/v1",
                    "attempt_id": attempt_id, "start_hash": start.start_hash,
                    "exit_code": exit_code,
                    "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
                    "recorded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                conn.execute(
                    "INSERT INTO agent_local_kilo_container_terminals VALUES(?,?,?,?,?)",
                    (attempt_id, canonical_json(payload), sha256_payload(payload),
                     stdout_bytes, stderr_bytes),
                )
                conn.commit()
                return self._read_terminal(conn, attempt_id)
            except Exception:
                conn.rollback()
                raise
