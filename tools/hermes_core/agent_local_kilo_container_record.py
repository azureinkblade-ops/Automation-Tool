"""Durable reported created-container identity, before any execution claim."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass

from tools.hermes_core.agent_local_kilo_fake_launch_candidate import (
    build_agent_local_kilo_fake_launch_candidate,
)
from tools.hermes_core.agent_local_kilo_fake_prestart import (
    inspect_agent_local_kilo_fake_prestart,
)
from tools.hermes_core.agent_local_kilo_ping_intent import (
    SQLiteAgentLocalKiloPingIntentStore,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import canonical_json, sha256_payload


_DDL = """CREATE TABLE IF NOT EXISTS agent_local_kilo_created_reports (
    attempt_id TEXT PRIMARY KEY,
    container_id TEXT NOT NULL UNIQUE,
    network_id TEXT NOT NULL UNIQUE,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_ID = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema_id", "attempt_id", "intent_hash", "candidate_hash",
    "container_id", "network_id", "observed_container_hash",
    "observed_image_hash", "launch_authorized",
})


@dataclass(frozen=True)
class ReportedCreatedKiloContainer:
    attempt_id: str
    intent_hash: str
    candidate_hash: str
    container_id: str
    network_id: str
    payload_sha256: str
    launch_authorized: bool = False


class SQLiteAgentLocalKiloContainerRecordStore:
    """Record one untrusted report; do not create, inspect, or start Docker."""

    def __init__(self, intents: SQLiteAgentLocalKiloPingIntentStore):
        if type(intents) is not SQLiteAgentLocalKiloPingIntentStore:
            raise DelegationIntegrityError("Kilo container record intent store denied")
        self.intents = intents
        with closing(self._connect()) as conn:
            conn.execute(_DDL)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.intents.bridge_store.authority.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @staticmethod
    def _read(conn, attempt_id):
        row = conn.execute(
            "SELECT container_id,network_id,canonical_payload,payload_sha256 "
            "FROM agent_local_kilo_created_reports WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[2])
            if (type(payload) is not dict or set(payload) != _FIELDS
                    or payload["schema_id"] != "hermes.agent-local-kilo-created-report/v1"
                    or payload["attempt_id"] != attempt_id
                    or payload["container_id"] != row[0]
                    or payload["network_id"] != row[1]
                    or payload["launch_authorized"] is not False
                    or any(type(payload[key]) is not str or not _ID.fullmatch(payload[key])
                           for key in (
                               "intent_hash", "candidate_hash", "container_id",
                               "network_id", "observed_container_hash", "observed_image_hash",
                           ))
                    or canonical_json(payload) != row[2]
                    or sha256_payload(payload) != row[3]):
                raise DelegationIntegrityError("Kilo created report integrity mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise DelegationIntegrityError("Kilo created report integrity mismatch") from exc
        return ReportedCreatedKiloContainer(
            attempt_id, payload["intent_hash"], payload["candidate_hash"],
            payload["container_id"], payload["network_id"], row[3],
        )

    def get(self, attempt_id: str) -> ReportedCreatedKiloContainer | None:
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("Kilo created report attempt missing")
        with closing(self._connect()) as conn:
            return self._read(conn, attempt_id)

    def record(self, attempt_id: str, v1_plan: dict, prepared: dict,
               container: dict, image: dict) -> ReportedCreatedKiloContainer:
        """Persist an exact reported identity; never grant a start permit."""
        intent = self.intents.verify_plan(attempt_id, v1_plan)
        candidate = build_agent_local_kilo_fake_launch_candidate(
            self.intents, attempt_id, v1_plan,
        )
        comparison = inspect_agent_local_kilo_fake_prestart(
            self.intents, attempt_id, v1_plan, prepared, container, image,
        )
        if comparison.reason != "CANDIDATE_METADATA_ONLY_START_DENIED":
            raise DelegationIntegrityError("Kilo created report metadata denied")
        try:
            container_id = container["Id"]
            network = container["NetworkSettings"]["Networks"][candidate["network"]["name"]]
            network_id = network["NetworkID"]
            if (type(container_id) is not str or not _ID.fullmatch(container_id)
                    or type(network_id) is not str or not _ID.fullmatch(network_id)):
                raise DelegationIntegrityError("Kilo created report identity denied")
            observed_container_hash = sha256_payload(container)
            observed_image_hash = sha256_payload(image)
        except (KeyError, TypeError, ValueError) as exc:
            raise DelegationIntegrityError("Kilo created report identity denied") from exc
        witness = load_bound_agent_start(
            self.intents.bridge_store.authority,
            self.intents.bridge_store.start, attempt_id,
        )
        bridge = self.intents.bridge_store.get(attempt_id)
        if bridge is None:
            raise DelegationIntegrityError("Kilo created report bridge absent")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if self._read(conn, attempt_id) is not None:
                    raise DelegationIntegrityError("Kilo created report already recorded")
                current_intent = SQLiteAgentLocalKiloPingIntentStore._read(conn, attempt_id)
                self.intents._active(conn, witness, bridge)
                self.intents._check_preclaim_window(conn, witness)
                if current_intent != intent or intent.bridge_hash != bridge.artifact_hash:
                    raise DelegationIntegrityError("Kilo created report intent changed")
                payload = {
                    "schema_id": "hermes.agent-local-kilo-created-report/v1",
                    "attempt_id": attempt_id,
                    "intent_hash": intent.payload_sha256,
                    "candidate_hash": candidate["candidate_hash"],
                    "container_id": container_id,
                    "network_id": network_id,
                    "observed_container_hash": observed_container_hash,
                    "observed_image_hash": observed_image_hash,
                    "launch_authorized": False,
                }
                conn.execute(
                    "INSERT INTO agent_local_kilo_created_reports VALUES(?,?,?,?,?)",
                    (attempt_id, container_id, network_id,
                     canonical_json(payload), sha256_payload(payload)),
                )
                conn.commit()
                return self._read(conn, attempt_id)
            except Exception:
                conn.rollback()
                raise
