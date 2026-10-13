"""Attempt-unique durable reservation of a non-launchable Linux Kilo ping plan."""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_local_kilo_ping_plan import verify_agent_local_kilo_ping_plan
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.hashing import canonical_json, sha256_payload


_DDL = """CREATE TABLE IF NOT EXISTS agent_local_kilo_ping_intents (
    attempt_id TEXT PRIMARY KEY,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_FIELDS = frozenset({
    "schema_version", "attempt_id", "bridge_hash", "plan_hash",
    "plan", "reserved_at",
})


@dataclass(frozen=True)
class AgentLocalKiloPingIntent:
    attempt_id: str
    bridge_hash: str
    plan_hash: str
    payload_sha256: str


class SQLiteAgentLocalKiloPingIntentStore:
    def __init__(self, bridge_store: SQLiteAgentInvocationBridgeStore, *, clock=None):
        if type(bridge_store) is not SQLiteAgentInvocationBridgeStore:
            raise DelegationIntegrityError("Linux Kilo intent bridge store denied")
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
    def _read(conn, attempt_id):
        row = conn.execute(
            "SELECT canonical_payload,payload_sha256 FROM agent_local_kilo_ping_intents "
            "WHERE attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
            plan = payload["plan"]
            if (type(payload) is not dict or set(payload) != _FIELDS
                    or payload["schema_version"] != "ea4e92ib-local-kilo-ping-intent-v1"
                    or payload["attempt_id"] != attempt_id
                    or type(plan) is not dict
                    or plan.get("attempt_id") != attempt_id
                    or payload["bridge_hash"] != plan.get("bridge_hash")
                    or payload["plan_hash"] != plan.get("plan_hash")
                    or plan.get("launch_authorized") is not False
                    or canonical_json(plan) != canonical_json({
                        **plan, "plan_hash": sha256_payload({
                            key: value for key, value in plan.items() if key != "plan_hash"
                        }),
                    })
                    or canonical_json(payload) != row[0]
                    or sha256_payload(payload) != row[1]):
                raise DelegationIntegrityError("Linux Kilo intent integrity mismatch")
            _parse_timestamp(payload["reserved_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DelegationIntegrityError("Linux Kilo intent integrity mismatch") from exc
        return AgentLocalKiloPingIntent(
            attempt_id, payload["bridge_hash"], payload["plan_hash"], row[1],
        )

    def get(self, attempt_id: str) -> AgentLocalKiloPingIntent | None:
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("Linux Kilo intent attempt missing")
        with closing(self._connect()) as conn:
            return self._read(conn, attempt_id)

    @staticmethod
    def _active(conn, witness, bridge):
        attempt_id = witness.lease.attempt_id
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
            raise DelegationIntegrityError("Linux Kilo intent authority changed")

    @staticmethod
    def _exists(conn, table, attempt_id):
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
        ).fetchone():
            return conn.execute(
                f"SELECT 1 FROM {table} WHERE attempt_id=?", (attempt_id,),
            ).fetchone() is not None
        return False

    def reserve(self, attempt_id: str, plan: dict) -> AgentLocalKiloPingIntent:
        """Reserve a complete candidate before any claim; never start Docker."""
        witness = load_bound_agent_start(
            self.bridge_store.authority, self.bridge_store.start, attempt_id,
        )
        bridge = self.bridge_store.get(attempt_id)
        if bridge is None:
            raise DelegationIntegrityError("Linux Kilo intent bridge absent")
        plan_hash = verify_agent_local_kilo_ping_plan(witness, bridge, plan)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if self._read(conn, attempt_id) is not None:
                    raise DelegationIntegrityError("Linux Kilo intent already reserved")
                self._active(conn, witness, bridge)
                now = self._clock()
                if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
                    raise DelegationIntegrityError("Linux Kilo intent clock invalid")
                now = now.astimezone(timezone.utc).replace(microsecond=0)
                if not (_parse_timestamp(witness.start_result.recorded_at) <= now
                        < _parse_timestamp(witness.lease.expires_at)):
                    raise DelegationIntegrityError("Linux Kilo intent outside lease window")
                for table in (
                    "agent_text_process_intents", "agent_invocation_claim_intents",
                    "agent_receiver_start_fences", "agent_terminal_captures",
                    "delegation_results",
                ):
                    if self._exists(conn, table, attempt_id):
                        raise DelegationIntegrityError("Linux Kilo intent too late or conflicting")
                payload = {
                    "schema_version": "ea4e92ib-local-kilo-ping-intent-v1",
                    "attempt_id": attempt_id, "bridge_hash": bridge.artifact_hash,
                    "plan_hash": plan_hash, "plan": plan,
                    "reserved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                digest = sha256_payload(payload)
                conn.execute(
                    "INSERT INTO agent_local_kilo_ping_intents VALUES(?,?,?)",
                    (attempt_id, canonical_json(payload), digest),
                )
                conn.commit()
                return AgentLocalKiloPingIntent(
                    attempt_id, bridge.artifact_hash, plan_hash, digest,
                )
            except Exception:
                conn.rollback()
                raise

    def verify_plan(self, attempt_id: str, plan: dict) -> AgentLocalKiloPingIntent:
        """Recheck reserved bytes and current authority; grant no launch permit."""
        witness = load_bound_agent_start(
            self.bridge_store.authority, self.bridge_store.start, attempt_id,
        )
        bridge = self.bridge_store.get(attempt_id)
        if bridge is None:
            raise DelegationIntegrityError("Linux Kilo intent bridge absent")
        plan_hash = verify_agent_local_kilo_ping_plan(witness, bridge, plan)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            intent = self._read(conn, attempt_id)
            self._active(conn, witness, bridge)
            row = conn.execute(
                "SELECT canonical_payload FROM agent_local_kilo_ping_intents "
                "WHERE attempt_id=?", (attempt_id,),
            ).fetchone()
            if (intent is None or intent.bridge_hash != bridge.artifact_hash
                    or intent.plan_hash != plan_hash
                    or canonical_json(json.loads(row[0])["plan"]) != canonical_json(plan)):
                raise DelegationIntegrityError("Linux Kilo reserved plan mismatch")
            return intent
