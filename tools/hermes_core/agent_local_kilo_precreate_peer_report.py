"""Durable untrusted pre-create peer report, never an ownership claim."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass

from tools.hermes_core.agent_local_kilo_ping_intent import (
    SQLiteAgentLocalKiloPingIntentStore,
)
from tools.hermes_core.agent_local_kilo_precreate_peer_review import (
    review_precreate_kilo_peer,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import canonical_json, sha256_payload


_ID = re.compile(r"[0-9a-f]{64}\Z")
_DDL = """CREATE TABLE IF NOT EXISTS agent_local_kilo_precreate_peer_reports (
    attempt_id TEXT PRIMARY KEY,
    network_id TEXT NOT NULL UNIQUE,
    gateway_id TEXT NOT NULL UNIQUE,
    canonical_payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);"""
_FIELDS = frozenset({
    "schema_id", "attempt_id", "issue_request_hash", "network_id",
    "gateway_id", "network_hash", "gateway_hash", "image_hash",
    "ownership_verified", "create_authorized", "launch_authorized",
})


@dataclass(frozen=True)
class ReportedPrecreateKiloPeer:
    attempt_id: str
    network_id: str
    gateway_id: str
    issue_request_hash: str
    payload_sha256: str
    ownership_verified: bool = False
    create_authorized: bool = False
    launch_authorized: bool = False


class _ReportedReadClient:
    def __init__(self, network, gateway, image):
        self.network, self.gateway, self.image = network, gateway, image

    def inspect_network(self, _identity):
        return self.network

    def inspect_container(self, _identity):
        return self.gateway

    def inspect_image(self, _index, _manifest):
        return self.image


class SQLiteAgentLocalKiloPrecreatePeerReportStore:
    """Persist one checked caller report; no daemon read or mutation capability."""

    def __init__(self, intents: SQLiteAgentLocalKiloPingIntentStore):
        if type(intents) is not SQLiteAgentLocalKiloPingIntentStore:
            raise DelegationIntegrityError("Kilo peer report intent store denied")
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
            "SELECT network_id,gateway_id,canonical_payload,payload_sha256 "
            "FROM agent_local_kilo_precreate_peer_reports WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[2])
            if (type(payload) is not dict or set(payload) != _FIELDS
                    or payload["schema_id"] != "hermes.agent-local-kilo-precreate-peer-report/v1"
                    or payload["attempt_id"] != attempt_id
                    or payload["network_id"] != row[0]
                    or payload["gateway_id"] != row[1]
                    or any(type(payload[key]) is not str or not _ID.fullmatch(payload[key])
                           for key in (
                               "issue_request_hash", "network_id", "gateway_id",
                               "network_hash", "gateway_hash", "image_hash",
                           ))
                    or any(payload[key] is not False for key in (
                        "ownership_verified", "create_authorized", "launch_authorized",
                    ))
                    or canonical_json(payload) != row[2]
                    or sha256_payload(payload) != row[3]):
                raise DelegationIntegrityError("Kilo peer report integrity mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise DelegationIntegrityError("Kilo peer report integrity mismatch") from exc
        return ReportedPrecreateKiloPeer(
            attempt_id, row[0], row[1], payload["issue_request_hash"], row[3],
        )

    def get(self, attempt_id: str) -> ReportedPrecreateKiloPeer | None:
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("Kilo peer report attempt missing")
        with closing(self._connect()) as conn:
            return self._read(conn, attempt_id)

    def record(self, attempt_id, v1_plan, prepared, spec, issue_request,
               network, gateway, image) -> ReportedPrecreateKiloPeer:
        if any(type(value) is not dict for value in (
            issue_request, network, gateway, image,
        )):
            raise DelegationIntegrityError("Kilo peer report shape denied")
        comparison = review_precreate_kilo_peer(
            self.intents, attempt_id, v1_plan, prepared, spec, issue_request,
            read_client=_ReportedReadClient(network, gateway, image),
        )
        if comparison.reason != "PRECREATE_METADATA_MATCH_OWNERSHIP_UNPROVEN":
            raise DelegationIntegrityError("Kilo peer report metadata denied")
        witness = load_bound_agent_start(
            self.intents.bridge_store.authority,
            self.intents.bridge_store.start, attempt_id,
        )
        bridge = self.intents.bridge_store.get(attempt_id)
        if bridge is None:
            raise DelegationIntegrityError("Kilo peer report bridge absent")
        payload = {
            "schema_id": "hermes.agent-local-kilo-precreate-peer-report/v1",
            "attempt_id": attempt_id,
            "issue_request_hash": issue_request["request_hash"],
            "network_id": issue_request["network_id"],
            "gateway_id": issue_request["gateway_id"],
            "network_hash": sha256_payload(network),
            "gateway_hash": sha256_payload(gateway),
            "image_hash": sha256_payload(image),
            "ownership_verified": False,
            "create_authorized": False,
            "launch_authorized": False,
        }
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if self._read(conn, attempt_id) is not None:
                    raise DelegationIntegrityError("Kilo peer report already recorded")
                self.intents._active(conn, witness, bridge)
                self.intents._check_preclaim_window(conn, witness)
                intent = SQLiteAgentLocalKiloPingIntentStore._read(conn, attempt_id)
                if (intent is None
                        or intent.payload_sha256 != issue_request["intent_hash"]):
                    raise DelegationIntegrityError("Kilo peer report intent changed")
                digest = sha256_payload(payload)
                conn.execute(
                    "INSERT INTO agent_local_kilo_precreate_peer_reports VALUES(?,?,?,?,?)",
                    (attempt_id, payload["network_id"], payload["gateway_id"],
                     canonical_json(payload), digest),
                )
                conn.commit()
                return ReportedPrecreateKiloPeer(
                    attempt_id, payload["network_id"], payload["gateway_id"],
                    payload["issue_request_hash"], digest,
                )
            except Exception:
                conn.rollback()
                raise
