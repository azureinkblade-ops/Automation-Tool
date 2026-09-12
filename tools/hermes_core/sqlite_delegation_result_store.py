"""Durable terminal-result and originator-delivery extension for R12E.

Uses the same SQLite database as ``SQLiteDelegationStore`` and atomically binds
the verified result, delivery identity, and RESULT_DELIVERY mailbox message.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .delegated_task import (
    DelegationIntegrityError,
    DelegationNotFoundError,
    reconstruct_capability_lease,
)
from .delegation_delivery import build_mailbox_message, reconstruct_delegation_receipt
from .delegation_result import (
    DelegationResult, DelegationResultConflictError, ResultDelivery,
    ResultDeliveryConflictError, build_result_delivery,
    reconstruct_delegation_result, reconstruct_result_delivery,
)
from .hashing import canonical_json, sha256_payload

RESULT_SCHEMA_VERSION = 1


class DelegationResultStoreError(RuntimeError): pass


DDL = """
CREATE TABLE IF NOT EXISTS delegation_result_schema_version (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS delegation_results (
  result_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL,
  delegation_id TEXT NOT NULL REFERENCES delegations(delegation_id),
  attempt_id TEXT NOT NULL UNIQUE,
  receipt_id TEXT NOT NULL REFERENCES delegation_receipts(receipt_id),
  runtime_run_id TEXT NOT NULL, outcome TEXT NOT NULL,
  validated_schema_id TEXT NOT NULL,
  verification_state TEXT NOT NULL CHECK(verification_state='RESULT_VERIFIED'),
  canonical_payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS result_deliveries (
  result_delivery_id TEXT PRIMARY KEY, artifact_hash TEXT NOT NULL,
  result_id TEXT NOT NULL REFERENCES delegation_results(result_id),
  recipient_agent_id TEXT NOT NULL, delivery_revision INTEGER NOT NULL,
  source_message_id TEXT NOT NULL REFERENCES agent_mailbox_messages(message_id),
  canonical_payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
  UNIQUE(result_id,recipient_agent_id,delivery_revision));
"""


class SQLiteDelegationResultStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._initialize()
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
    def _initialize(self):
        if not self.path.exists(): raise DelegationResultStoreError("delegation authority database must already exist")
        with closing(self._connect()) as conn:
            required = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"delegations","capability_leases","delegation_receipts","agent_mailbox_messages"}.issubset(required):
                raise DelegationResultStoreError("delegation authority schema is incomplete")
            conn.executescript(DDL)
            row = conn.execute("SELECT version FROM delegation_result_schema_version WHERE singleton=1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO delegation_result_schema_version VALUES(1,?)",
                    (RESULT_SCHEMA_VERSION,),
                )
            elif row["version"] != RESULT_SCHEMA_VERSION:
                raise DelegationResultStoreError("unsupported result schema version")
            conn.commit()
    @staticmethod
    def _decode(row, kind):
        try: payload = json.loads(row["canonical_payload"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DelegationIntegrityError(f"{kind} payload corrupt") from exc
        if canonical_json(payload) != row["canonical_payload"] or sha256_payload(payload) != row["payload_sha256"]:
            raise DelegationIntegrityError(f"{kind} payload checksum mismatch")
        return payload
    def _load_result(self, row):
        result = reconstruct_delegation_result(self._decode(row,"result"))
        if row["result_id"] != result.result_id or row["artifact_hash"] != result.artifact_hash or row["attempt_id"] != result.attempt_id or row["verification_state"] != "RESULT_VERIFIED":
            raise DelegationIntegrityError("result physical linkage mismatch")
        return result
    def _load_delivery(self, row):
        delivery = reconstruct_result_delivery(self._decode(row,"result delivery"))
        if row["result_delivery_id"] != delivery.result_delivery_id or row["artifact_hash"] != delivery.artifact_hash:
            raise DelegationIntegrityError("result delivery physical linkage mismatch")
        return delivery
    def get_result(self, attempt_id: str):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM delegation_results WHERE attempt_id=?",(attempt_id,)).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"result not found for attempt: {attempt_id}")
        return self._load_result(row)
    def get_delivery(self, result_delivery_id: str):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM result_deliveries WHERE result_delivery_id=?",(result_delivery_id,)).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"result delivery not found: {result_delivery_id}")
        return self._load_delivery(row)
    @staticmethod
    def _verify_result_contract(result, envelope, lease, validated_result_schema_id):
        if validated_result_schema_id != envelope["expected_result_schema_id"]:
            raise DelegationIntegrityError("result schema was not validated against the delegation contract")
        if validated_result_schema_id != lease.expected_result_schema_id:
            raise DelegationIntegrityError("result schema does not match the capability lease")
        allowed_outputs = set(lease.permitted_write_paths)
        for output in result.output_manifest:
            if output["reference_type"] == "workspace_file" and output["reference"] not in allowed_outputs:
                raise DelegationIntegrityError("result output is outside delegated write scope")
        actual_evidence = result.evidence_manifest
        for expected in envelope["expected_evidence"]:
            required = {key: value for key, value in expected.items() if key != "ordinal"}
            if not any(all(candidate.get(key) == value for key, value in required.items()) for candidate in actual_evidence):
                raise DelegationIntegrityError("result is missing required evidence")

    def delegation_projection(self, delegation_id: str) -> str:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM delegation_results WHERE delegation_id=?",
                (delegation_id,),
            ).fetchone()
        if row is None:
            raise DelegationNotFoundError(f"verified result not found for delegation: {delegation_id}")
        result = self._load_result(row)
        return {"SUCCEEDED": "COMPLETED", "FAILED": "FAILED", "CANCELLED": "CANCELLED"}[result.outcome]

    def record_verified_result_and_delivery(
        self,
        result: DelegationResult,
        *,
        validated_result_schema_id: str,
        delivered_at: str,
    ):
        result.verify_hash()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute("SELECT * FROM delegation_results WHERE attempt_id=?",(result.attempt_id,)).fetchone()
                if existing:
                    durable = self._load_result(existing)
                    if durable.artifact_hash != result.artifact_hash:
                        raise DelegationResultConflictError("attempt has divergent result")
                    if existing["validated_schema_id"] != validated_result_schema_id:
                        raise DelegationResultConflictError("attempt has divergent schema verification")
                    delivery_row = conn.execute("SELECT * FROM result_deliveries WHERE result_id=?",(result.result_id,)).fetchone()
                    if delivery_row is None:
                        raise DelegationIntegrityError("result exists without durable delivery")
                    delivery = self._load_delivery(delivery_row)
                    message_row = conn.execute(
                        "SELECT * FROM agent_mailbox_messages WHERE message_id=?",
                        (delivery_row["source_message_id"],),
                    ).fetchone()
                    if message_row is None:
                        raise DelegationIntegrityError("result delivery message is missing")
                    body = {
                        "result": durable.to_canonical_dict(),
                        "result_delivery": delivery.to_canonical_dict(),
                    }
                    if (
                        message_row["message_type"] != "RESULT_DELIVERY"
                        or message_row["recipient_agent_id"] != delivery.recipient_agent_id
                        or message_row["message_body"] != canonical_json(body)
                        or message_row["message_body_sha256"] != sha256_payload(body)
                    ):
                        raise DelegationIntegrityError("result delivery message linkage mismatch")
                    conn.rollback()
                    return durable, delivery, delivery_row["source_message_id"]
                receipt_row = conn.execute("SELECT * FROM delegation_receipts WHERE attempt_id=?",(result.attempt_id,)).fetchone()
                delegation_row = conn.execute("SELECT * FROM delegations WHERE delegation_id=?",(result.delegation_id,)).fetchone()
                if receipt_row is None or delegation_row is None:
                    raise DelegationIntegrityError("result lineage is incomplete")
                receipt = reconstruct_delegation_receipt(self._decode(receipt_row,"receipt"))
                envelope = self._decode(delegation_row,"delegation")
                lease_row = conn.execute(
                    "SELECT * FROM capability_leases WHERE lease_id=?",
                    (receipt.capability_lease_id,),
                ).fetchone()
                if lease_row is None:
                    raise DelegationIntegrityError("result capability lease is missing")
                lease = reconstruct_capability_lease(self._decode(lease_row, "lease"))
                checks = (
                    (result.delegation_id, receipt.delegation_id),
                    (result.delegated_task_hash, envelope["artifact_hash"]),
                    (result.delegated_task_hash, receipt.delegated_task_hash),
                    (result.receipt_id,receipt.receipt_id),
                    (result.receipt_hash,receipt.artifact_hash), (result.authorization_id,receipt.authorization_id),
                    (result.authorization_hash,receipt.authorization_hash), (result.attempt_id,receipt.attempt_id),
                    (result.attempt_hash,receipt.attempt_hash), (result.launch_attempt_id,receipt.launch_attempt_id),
                    (result.launch_attempt_hash,receipt.launch_attempt_hash), (result.receiver_agent_id,receipt.receiver_agent_id),
                    (result.receiver_descriptor_hash,receipt.receiver_descriptor_hash), (result.runtime_run_id,receipt.runtime_run_id),
                )
                if receipt.outcome != "ACCEPTED" or any(a != b for a,b in checks):
                    raise DelegationIntegrityError("result lineage mismatch")
                self._verify_result_contract(result, envelope, lease, validated_result_schema_id)
                text, checksum = canonical_json(result.to_canonical_dict()), sha256_payload(result.to_canonical_dict())
                conn.execute("INSERT INTO delegation_results VALUES(?,?,?,?,?,?,?,?, 'RESULT_VERIFIED',?,?)",
                    (result.result_id,result.artifact_hash,result.delegation_id,result.attempt_id,result.receipt_id,result.runtime_run_id,result.outcome,validated_result_schema_id,text,checksum))
                recipient = delegation_row["originator_agent_id"]
                delivery = build_result_delivery(result_id=result.result_id,result_hash=result.artifact_hash,
                    recipient_agent_id=recipient,created_at=delivered_at)
                body = {"result":result.to_canonical_dict(),"result_delivery":delivery.to_canonical_dict()}
                body_text, body_hash = canonical_json(body), sha256_payload(body)
                sequence = conn.execute("SELECT COALESCE(MAX(mailbox_sequence),0)+1 FROM agent_mailbox_messages WHERE mailbox_id=?",(recipient,)).fetchone()[0]
                message = build_mailbox_message(mailbox_id=recipient,mailbox_sequence=sequence,message_type="RESULT_DELIVERY",
                    sender_agent_id="hermes-execution-authority",recipient_agent_id=recipient,delegation_id=result.delegation_id,
                    attempt_id=result.attempt_id,idempotency_key=delivery.result_delivery_id,payload_schema_id="hermes.result_delivery/v1",
                    payload_hash=body_hash,created_at=delivered_at)
                msg_text, msg_checksum = canonical_json(message.to_canonical_dict()), sha256_payload(message.to_canonical_dict())
                conn.execute("INSERT INTO agent_mailbox_messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (message.message_id,message.artifact_hash,message.mailbox_id,message.mailbox_sequence,message.message_type,
                     message.sender_agent_id,message.recipient_agent_id,message.delegation_id,message.attempt_id,message.idempotency_key,
                     message.payload_schema_id,message.payload_hash,message.created_at,msg_text,msg_checksum,body_text,body_hash))
                dtext, dchecksum = canonical_json(delivery.to_canonical_dict()), sha256_payload(delivery.to_canonical_dict())
                conn.execute("INSERT INTO result_deliveries VALUES(?,?,?,?,?,?,?,?)",
                    (delivery.result_delivery_id,delivery.artifact_hash,delivery.result_id,delivery.recipient_agent_id,
                     delivery.delivery_revision,message.message_id,dtext,dchecksum))
                conn.commit(); return result, delivery, message.message_id
            except sqlite3.IntegrityError as exc:
                conn.rollback(); raise ResultDeliveryConflictError("result/delivery uniqueness conflict") from exc
            except Exception:
                conn.rollback(); raise
