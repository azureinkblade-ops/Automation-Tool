"""Canonical terminal result and originator-delivery artifacts for R12E."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Optional

from .delegated_task import (
    ARTIFACT_VERSION, DelegationDomainError, DelegationIntegrityError,
    InvalidCanonicalEnvelopeError, _normalize_hash, _normalize_json,
    _normalize_ordered_records, _normalize_text, _normalize_timestamp,
    _parse_timestamp,
)
from .hashing import sha256_payload

RESULT_ARTIFACT_TYPE = "hermes.delegation_result"
RESULT_DELIVERY_ARTIFACT_TYPE = "hermes.result_delivery"
RESULT_OUTCOMES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})


class DelegationResultConflictError(DelegationDomainError):
    """An execution attempt already has a different terminal result."""


class ResultDeliveryConflictError(DelegationDomainError):
    """A result-delivery identity already has different durable material."""


@dataclass(frozen=True)
class DelegationResult:
    result_id: str
    delegation_id: str
    delegated_task_hash: str
    authorization_id: str
    authorization_hash: str
    attempt_id: str
    attempt_hash: str
    launch_attempt_id: str
    launch_attempt_hash: str
    receipt_id: str
    receipt_hash: str
    receiver_agent_id: str
    receiver_descriptor_hash: str
    runtime_run_id: str
    outcome: str
    result_payload: dict[str, Any]
    output_manifest: tuple[dict[str, Any], ...]
    evidence_manifest: tuple[dict[str, Any], ...]
    started_at: str
    completed_at: str
    error_code: Optional[str]
    error_summary: Optional[str]
    artifact_type: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self, *, include_id=True, include_hash=True):
        data = {k: getattr(self, k) for k in self.__dataclass_fields__ if k not in {"result_id", "artifact_hash"}}
        data["output_manifest"] = [dict(x) for x in self.output_manifest]
        data["evidence_manifest"] = [dict(x) for x in self.evidence_manifest]
        if include_id: data["result_id"] = self.result_id
        if include_hash: data["artifact_hash"] = self.artifact_hash
        return data

    def verify_hash(self):
        expected = f"result-{sha256_payload(self.to_canonical_dict(include_id=False, include_hash=False))}"
        if self.result_id != expected or sha256_payload(self.to_canonical_dict(include_hash=False)) != self.artifact_hash:
            raise DelegationIntegrityError("delegation result identity or hash mismatch")


def build_delegation_result(**v) -> DelegationResult:
    outcome = _normalize_text(v["outcome"], "outcome")
    if outcome not in RESULT_OUTCOMES: raise InvalidCanonicalEnvelopeError("unsupported result outcome")
    code, summary = v.get("error_code"), v.get("error_summary")
    if outcome == "FAILED":
        code, summary = _normalize_text(code, "error_code"), _normalize_text(summary, "error_summary")
    elif code is not None or summary is not None:
        raise InvalidCanonicalEnvelopeError("non-failed result cannot carry error fields")
    started, completed = _normalize_timestamp(v["started_at"], "started_at"), _normalize_timestamp(v["completed_at"], "completed_at")
    if _parse_timestamp(completed) < _parse_timestamp(started): raise InvalidCanonicalEnvelopeError("completed_at precedes started_at")
    result_payload = _normalize_json(v["result_payload"], "result_payload")
    if not isinstance(result_payload, dict):
        raise InvalidCanonicalEnvelopeError("result_payload must be an object")
    output_manifest = _normalize_ordered_records(v["output_manifest"], "output_manifest")
    evidence_manifest = _normalize_ordered_records(v["evidence_manifest"], "evidence_manifest")
    for entry in output_manifest:
        if set(entry) != {"ordinal", "reference_type", "reference", "sha256", "media_type"}:
            raise InvalidCanonicalEnvelopeError("output_manifest entries have invalid fields")
        _normalize_text(entry["reference_type"], "output_manifest.reference_type")
        _normalize_text(entry["reference"], "output_manifest.reference")
        _normalize_hash(entry["sha256"], "output_manifest.sha256")
        _normalize_text(entry["media_type"], "output_manifest.media_type")
    for entry in evidence_manifest:
        if set(entry) != {"ordinal", "evidence_type", "sha256"}:
            raise InvalidCanonicalEnvelopeError("evidence_manifest entries have invalid fields")
        _normalize_text(entry["evidence_type"], "evidence_manifest.evidence_type")
        _normalize_hash(entry["sha256"], "evidence_manifest.sha256")
    result = DelegationResult(
        result_id="", delegation_id=_normalize_text(v["delegation_id"], "delegation_id"),
        delegated_task_hash=_normalize_hash(v["delegated_task_hash"], "delegated_task_hash"),
        authorization_id=_normalize_text(v["authorization_id"], "authorization_id"),
        authorization_hash=_normalize_hash(v["authorization_hash"], "authorization_hash"),
        attempt_id=_normalize_text(v["attempt_id"], "attempt_id"), attempt_hash=_normalize_hash(v["attempt_hash"], "attempt_hash"),
        launch_attempt_id=_normalize_text(v["launch_attempt_id"], "launch_attempt_id"),
        launch_attempt_hash=_normalize_hash(v["launch_attempt_hash"], "launch_attempt_hash"),
        receipt_id=_normalize_text(v["receipt_id"], "receipt_id"), receipt_hash=_normalize_hash(v["receipt_hash"], "receipt_hash"),
        receiver_agent_id=_normalize_text(v["receiver_agent_id"], "receiver_agent_id"),
        receiver_descriptor_hash=_normalize_hash(v["receiver_descriptor_hash"], "receiver_descriptor_hash"),
        runtime_run_id=_normalize_text(v["runtime_run_id"], "runtime_run_id"), outcome=outcome,
        result_payload=result_payload,
        output_manifest=output_manifest,
        evidence_manifest=evidence_manifest,
        started_at=started, completed_at=completed, error_code=code, error_summary=summary,
        artifact_type=RESULT_ARTIFACT_TYPE, artifact_version=ARTIFACT_VERSION, artifact_hash="",
    )
    result = replace(result, result_id=f"result-{sha256_payload(result.to_canonical_dict(include_id=False, include_hash=False))}")
    return replace(result, artifact_hash=sha256_payload(result.to_canonical_dict(include_hash=False)))


def reconstruct_delegation_result(payload: Mapping[str, Any]) -> DelegationResult:
    required = set(DelegationResult.__dataclass_fields__)
    if not isinstance(payload, Mapping) or set(payload) != required: raise InvalidCanonicalEnvelopeError("invalid result fields")
    rebuilt = build_delegation_result(**{k: payload[k] for k in required if k not in {"result_id", "artifact_type", "artifact_version", "artifact_hash"}})
    if payload["artifact_type"] != RESULT_ARTIFACT_TYPE or payload["artifact_version"] != ARTIFACT_VERSION or payload["result_id"] != rebuilt.result_id or payload["artifact_hash"] != rebuilt.artifact_hash:
        raise DelegationIntegrityError("delegation result reconstruction mismatch")
    return rebuilt


@dataclass(frozen=True)
class ResultDelivery:
    result_delivery_id: str
    result_id: str
    result_hash: str
    recipient_agent_id: str
    delivery_revision: int
    created_at: str
    artifact_type: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self, *, include_id=True, include_hash=True):
        data = {k: getattr(self, k) for k in self.__dataclass_fields__ if k not in {"result_delivery_id", "artifact_hash"}}
        if include_id: data["result_delivery_id"] = self.result_delivery_id
        if include_hash: data["artifact_hash"] = self.artifact_hash
        return data
    def verify_hash(self):
        expected = f"delivery-{sha256_payload({'result_id': self.result_id, 'recipient_agent_id': self.recipient_agent_id, 'delivery_revision': self.delivery_revision})}"
        if self.result_delivery_id != expected or sha256_payload(self.to_canonical_dict(include_hash=False)) != self.artifact_hash:
            raise DelegationIntegrityError("result delivery identity or hash mismatch")


def build_result_delivery(*, result_id, result_hash, recipient_agent_id, created_at, delivery_revision=0):
    if delivery_revision != 0: raise InvalidCanonicalEnvelopeError("first implementation requires delivery_revision=0")
    result_id, recipient = _normalize_text(result_id, "result_id"), _normalize_text(recipient_agent_id, "recipient_agent_id")
    delivery = ResultDelivery("", result_id, _normalize_hash(result_hash, "result_hash"), recipient, 0,
                              _normalize_timestamp(created_at, "created_at"), RESULT_DELIVERY_ARTIFACT_TYPE, ARTIFACT_VERSION, "")
    identity = {"result_id": result_id, "recipient_agent_id": recipient, "delivery_revision": 0}
    delivery = replace(delivery, result_delivery_id=f"delivery-{sha256_payload(identity)}")
    return replace(delivery, artifact_hash=sha256_payload(delivery.to_canonical_dict(include_hash=False)))


def reconstruct_result_delivery(payload: Mapping[str, Any]) -> ResultDelivery:
    required = set(ResultDelivery.__dataclass_fields__)
    if not isinstance(payload, Mapping) or set(payload) != required: raise InvalidCanonicalEnvelopeError("invalid result delivery fields")
    rebuilt = build_result_delivery(**{k: payload[k] for k in ("result_id", "result_hash", "recipient_agent_id", "created_at", "delivery_revision")})
    if payload["artifact_type"] != RESULT_DELIVERY_ARTIFACT_TYPE or payload["artifact_version"] != ARTIFACT_VERSION or payload["result_delivery_id"] != rebuilt.result_delivery_id or payload["artifact_hash"] != rebuilt.artifact_hash:
        raise DelegationIntegrityError("result delivery reconstruction mismatch")
    return rebuilt
