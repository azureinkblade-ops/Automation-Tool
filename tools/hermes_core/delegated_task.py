"""Canonical R12A delegation and bounded capability-lease domain.

This module is deliberately inert: it validates and hashes immutable artifacts.
It does not route, launch, schedule, call a network, or accept delegated work.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from .hashing import canonical_json, sha256_payload


DELEGATED_TASK_ARTIFACT_TYPE = "hermes.delegated_task"
CAPABILITY_LEASE_ARTIFACT_TYPE = "hermes.delegated_capability_lease"
ARTIFACT_VERSION = "1"
LEASE_ISSUER = "hermes-execution-authority"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class DelegationDomainError(ValueError):
    """Base class for R12A delegation-domain failures."""


class InvalidCanonicalEnvelopeError(DelegationDomainError):
    """Canonical material is malformed or unsafe."""


class DelegationConflictError(DelegationDomainError):
    """The same delegation identity was presented with divergent material."""


class DelegationNotFoundError(DelegationDomainError):
    """The requested durable delegation does not exist."""


class InvalidDelegationStateTransitionError(DelegationDomainError):
    """A requested delegation state transition is forbidden."""


class LeaseConflictError(DelegationDomainError):
    """The same lease identity was presented with divergent material."""


class LeaseExpiredError(DelegationDomainError):
    """The lease is expired at the requested capability-use time."""


class LeaseRevokedError(DelegationDomainError):
    """The lease has been durably revoked."""


class CapabilityViolationError(DelegationDomainError):
    """A requested operation would exceed the delegated capability."""


class CancellationConflictError(DelegationDomainError):
    """Cancellation or revocation replay conflicts with durable truth."""


class DelegationIntegrityError(DelegationDomainError):
    """Persisted or reconstructed artifact integrity verification failed."""


def _normalize_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InvalidCanonicalEnvelopeError(f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    if not allow_empty and not normalized:
        raise InvalidCanonicalEnvelopeError(f"{field} must not be empty")
    if any(line.endswith((" ", "\t")) for line in normalized.split("\n")):
        raise InvalidCanonicalEnvelopeError(f"{field} contains trailing whitespace")
    return normalized


def _normalize_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InvalidCanonicalEnvelopeError(f"{field} must be an integer >= {minimum}")
    return value


def _normalize_hash(value: Any, field: str) -> str:
    text = _normalize_text(value, field)
    if not _HASH_RE.fullmatch(text):
        raise InvalidCanonicalEnvelopeError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _normalize_timestamp(value: Any, field: str, *, optional: bool = False) -> Optional[str]:
    if value is None and optional:
        return None
    text = _normalize_text(value, field)
    if not _TIMESTAMP_RE.fullmatch(text):
        raise InvalidCanonicalEnvelopeError(
            f"{field} must be UTC RFC3339 at whole-second precision"
        )
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InvalidCanonicalEnvelopeError(f"{field} is not a valid timestamp") from exc
    return text


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _normalize_json(value: Any, field: str) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise InvalidCanonicalEnvelopeError(f"{field} contains NaN or infinity")
        raise InvalidCanonicalEnvelopeError(f"{field} contains a forbidden float")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise InvalidCanonicalEnvelopeError(f"{field} contains binary data")
    if isinstance(value, str):
        return _normalize_text(value, field, allow_empty=True)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = _normalize_text(raw_key, f"{field} key")
            if key in normalized:
                raise InvalidCanonicalEnvelopeError(f"{field} contains duplicate canonical key {key!r}")
            normalized[key] = _normalize_json(raw_value, f"{field}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item, f"{field}[]") for item in value]
    raise InvalidCanonicalEnvelopeError(f"{field} contains unsupported type {type(value).__name__}")


def _normalize_path(value: Any, field: str) -> str:
    path = _normalize_text(value, field)
    if "\\" in path or path.startswith("/") or _DRIVE_RE.match(path):
        raise InvalidCanonicalEnvelopeError(f"{field} must be a workspace-relative POSIX path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidCanonicalEnvelopeError(f"{field} contains a forbidden path segment")
    if ":" in parts[0]:
        raise InvalidCanonicalEnvelopeError(f"{field} must not contain a URI scheme or drive")
    return path


def _normalize_reference(value: Any, digest: str, field: str) -> str:
    reference = _normalize_text(value, field)
    if reference.startswith("sha256:"):
        embedded = reference.removeprefix("sha256:")
        if embedded != digest:
            raise InvalidCanonicalEnvelopeError(f"{field} content-addressed digest does not match sha256")
        return reference
    return _normalize_path(reference, field)


def _normalize_string_set(values: Iterable[Any], field: str, *, paths: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise InvalidCanonicalEnvelopeError(f"{field} must be a list")
    normalizer = _normalize_path if paths else _normalize_text
    return tuple(sorted({normalizer(value, f"{field}[]") for value in values}))


def _normalize_ordered_records(values: Iterable[Any], field: str) -> tuple[dict[str, Any], ...]:
    if isinstance(values, (str, bytes, Mapping)):
        raise InvalidCanonicalEnvelopeError(f"{field} must be an ordered list")
    records: list[dict[str, Any]] = []
    ordinals: set[int] = set()
    for raw in values:
        if not isinstance(raw, Mapping):
            raise InvalidCanonicalEnvelopeError(f"{field} entries must be objects")
        record = _normalize_json(raw, f"{field}[]")
        ordinal = _normalize_int(record.get("ordinal"), f"{field}.ordinal")
        if ordinal in ordinals:
            raise InvalidCanonicalEnvelopeError(f"{field} contains duplicate ordinal {ordinal}")
        ordinals.add(ordinal)
        records.append(record)
    if ordinals != set(range(len(records))):
        raise InvalidCanonicalEnvelopeError(f"{field} ordinals must be contiguous from zero")
    return tuple(sorted(records, key=lambda item: item["ordinal"]))


def _normalize_input_manifest(values: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    records = _normalize_ordered_records(values, "input_manifest")
    normalized: list[dict[str, Any]] = []
    required = {"ordinal", "reference_type", "reference", "sha256", "media_type"}
    for record in records:
        if set(record) != required:
            raise InvalidCanonicalEnvelopeError(
                "input_manifest entries require exactly ordinal, reference_type, reference, sha256, media_type"
            )
        digest = _normalize_hash(record["sha256"], "input_manifest.sha256")
        normalized.append(
            {
                "ordinal": record["ordinal"],
                "reference_type": _normalize_text(record["reference_type"], "input_manifest.reference_type"),
                "reference": _normalize_reference(record["reference"], digest, "input_manifest.reference"),
                "sha256": digest,
                "media_type": _normalize_text(record["media_type"], "input_manifest.media_type"),
            }
        )
    return tuple(normalized)


@dataclass(frozen=True)
class DelegationScope:
    read_paths: tuple[str, ...]
    write_paths: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    network_policy: str
    approved_hosts: tuple[str, ...]
    time_budget_seconds: int

    @classmethod
    def build(cls, value: Mapping[str, Any]) -> "DelegationScope":
        required = {
            "read_paths", "write_paths", "allowed_tools", "network_policy",
            "approved_hosts", "time_budget_seconds",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise InvalidCanonicalEnvelopeError(f"scope requires exactly {sorted(required)}")
        network_policy = _normalize_text(value["network_policy"], "scope.network_policy")
        approved_hosts = _normalize_string_set(value["approved_hosts"], "scope.approved_hosts")
        if network_policy == "deny" and approved_hosts:
            raise InvalidCanonicalEnvelopeError("scope.approved_hosts must be empty when network_policy is deny")
        if network_policy not in {"deny", "allowlist"}:
            raise InvalidCanonicalEnvelopeError("scope.network_policy must be deny or allowlist")
        return cls(
            read_paths=_normalize_string_set(value["read_paths"], "scope.read_paths", paths=True),
            write_paths=_normalize_string_set(value["write_paths"], "scope.write_paths", paths=True),
            allowed_tools=_normalize_string_set(value["allowed_tools"], "scope.allowed_tools"),
            network_policy=network_policy,
            approved_hosts=approved_hosts,
            time_budget_seconds=_normalize_int(value["time_budget_seconds"], "scope.time_budget_seconds", minimum=1),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "read_paths": list(self.read_paths),
            "write_paths": list(self.write_paths),
            "allowed_tools": list(self.allowed_tools),
            "network_policy": self.network_policy,
            "approved_hosts": list(self.approved_hosts),
            "time_budget_seconds": self.time_budget_seconds,
        }


@dataclass(frozen=True)
class DelegatedTaskEnvelope:
    artifact_type: str
    artifact_version: str
    delegation_id: str
    delegation_revision: int
    originator_request_id: str
    task_id: str
    parent_task_id: Optional[str]
    originator_agent_id: str
    requested_target_agent_id: str
    operation: str
    objective: str
    instructions: str
    input_manifest: tuple[dict[str, Any], ...]
    task_input_hash: str
    scope: DelegationScope
    expected_result_schema_id: str
    expected_evidence: tuple[dict[str, Any], ...]
    requested_at: str
    expires_at: Optional[str]
    redelegation_allowed: bool
    artifact_hash: str

    def to_canonical_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "delegation_id": self.delegation_id,
            "delegation_revision": self.delegation_revision,
            "originator_request_id": self.originator_request_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "originator_agent_id": self.originator_agent_id,
            "requested_target_agent_id": self.requested_target_agent_id,
            "operation": self.operation,
            "objective": self.objective,
            "instructions": self.instructions,
            "input_manifest": [dict(item) for item in self.input_manifest],
            "task_input_hash": self.task_input_hash,
            "scope": self.scope.to_canonical_dict(),
            "expected_result_schema_id": self.expected_result_schema_id,
            "expected_evidence": [dict(item) for item in self.expected_evidence],
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "redelegation_allowed": self.redelegation_allowed,
        }
        if include_hash:
            payload["artifact_hash"] = self.artifact_hash
        return payload

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> None:
        if sha256_payload(self.to_canonical_dict(include_hash=False)) != self.artifact_hash:
            raise DelegationIntegrityError("delegated task artifact hash mismatch")


def build_delegated_task_envelope(
    *,
    delegation_revision: int,
    originator_request_id: str,
    task_id: str,
    parent_task_id: Optional[str],
    originator_agent_id: str,
    requested_target_agent_id: str,
    operation: str,
    objective: str,
    instructions: str,
    input_manifest: Iterable[Mapping[str, Any]],
    scope: Mapping[str, Any] | DelegationScope,
    expected_result_schema_id: str,
    expected_evidence: Iterable[Mapping[str, Any]],
    requested_at: str,
    expires_at: Optional[str] = None,
    redelegation_allowed: bool = False,
) -> DelegatedTaskEnvelope:
    revision = _normalize_int(delegation_revision, "delegation_revision")
    originator = _normalize_text(originator_agent_id, "originator_agent_id")
    request_id = _normalize_text(originator_request_id, "originator_request_id")
    manifest = _normalize_input_manifest(input_manifest)
    evidence = _normalize_ordered_records(expected_evidence, "expected_evidence")
    normalized_scope = scope if isinstance(scope, DelegationScope) else DelegationScope.build(scope)
    requested = _normalize_timestamp(requested_at, "requested_at")
    expires = _normalize_timestamp(expires_at, "expires_at", optional=True)
    if expires is not None and _parse_timestamp(expires) <= _parse_timestamp(requested):
        raise InvalidCanonicalEnvelopeError("expires_at must be after requested_at")
    if redelegation_allowed is not False:
        raise InvalidCanonicalEnvelopeError("R12A requires redelegation_allowed=false")
    operation_text = _normalize_text(operation, "operation")
    objective_text = _normalize_text(objective, "objective")
    instructions_text = _normalize_text(instructions, "instructions", allow_empty=True)
    result_schema = _normalize_text(expected_result_schema_id, "expected_result_schema_id")
    identity_preimage = {
        "artifact_type": "hermes.delegation_identity",
        "artifact_version": ARTIFACT_VERSION,
        "delegation_revision": revision,
        "originator_agent_id": originator,
        "originator_request_id": request_id,
    }
    delegation_id = f"delegation-{sha256_payload(identity_preimage)}"
    task_input_hash = sha256_payload(
        {
            "operation": operation_text,
            "objective": objective_text,
            "instructions": instructions_text,
            "input_manifest": [dict(item) for item in manifest],
            "expected_result_schema_id": result_schema,
            "expected_evidence": [dict(item) for item in evidence],
        }
    )
    envelope = DelegatedTaskEnvelope(
        artifact_type=DELEGATED_TASK_ARTIFACT_TYPE,
        artifact_version=ARTIFACT_VERSION,
        delegation_id=delegation_id,
        delegation_revision=revision,
        originator_request_id=request_id,
        task_id=_normalize_text(task_id, "task_id"),
        parent_task_id=None if parent_task_id is None else _normalize_text(parent_task_id, "parent_task_id"),
        originator_agent_id=originator,
        requested_target_agent_id=_normalize_text(requested_target_agent_id, "requested_target_agent_id"),
        operation=operation_text,
        objective=objective_text,
        instructions=instructions_text,
        input_manifest=manifest,
        task_input_hash=task_input_hash,
        scope=normalized_scope,
        expected_result_schema_id=result_schema,
        expected_evidence=evidence,
        requested_at=requested,
        expires_at=expires,
        redelegation_allowed=False,
        artifact_hash="",
    )
    return replace(envelope, artifact_hash=sha256_payload(envelope.to_canonical_dict(include_hash=False)))


def reconstruct_delegated_task(payload: Mapping[str, Any]) -> DelegatedTaskEnvelope:
    required = set(DelegatedTaskEnvelope.__dataclass_fields__)
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise InvalidCanonicalEnvelopeError(f"delegated task requires exactly {sorted(required)}")
    rebuilt = build_delegated_task_envelope(
        delegation_revision=payload["delegation_revision"],
        originator_request_id=payload["originator_request_id"],
        task_id=payload["task_id"],
        parent_task_id=payload["parent_task_id"],
        originator_agent_id=payload["originator_agent_id"],
        requested_target_agent_id=payload["requested_target_agent_id"],
        operation=payload["operation"],
        objective=payload["objective"],
        instructions=payload["instructions"],
        input_manifest=payload["input_manifest"],
        scope=payload["scope"],
        expected_result_schema_id=payload["expected_result_schema_id"],
        expected_evidence=payload["expected_evidence"],
        requested_at=payload["requested_at"],
        expires_at=payload["expires_at"],
        redelegation_allowed=payload["redelegation_allowed"],
    )
    if payload["artifact_type"] != DELEGATED_TASK_ARTIFACT_TYPE or payload["artifact_version"] != ARTIFACT_VERSION:
        raise InvalidCanonicalEnvelopeError("unsupported delegated task schema")
    if payload["delegation_id"] != rebuilt.delegation_id:
        raise DelegationIntegrityError("delegation identity mismatch")
    if payload["task_input_hash"] != rebuilt.task_input_hash:
        raise DelegationIntegrityError("delegated task input hash mismatch")
    if payload["artifact_hash"] != rebuilt.artifact_hash:
        raise DelegationIntegrityError("delegated task artifact hash mismatch")
    return rebuilt


@dataclass(frozen=True)
class DelegatedCapabilityLease:
    artifact_type: str
    artifact_version: str
    lease_id: str
    issuer: str
    delegation_id: str
    delegated_task_hash: str
    authorization_id: str
    authorization_hash: str
    attempt_id: str
    attempt_hash: str
    route_id: str
    route_hash: str
    recipient_agent_id: str
    worker_descriptor_hash: str
    allowed_operation: str
    allowed_tools: tuple[str, ...]
    prohibited_tools: tuple[str, ...]
    permitted_read_paths: tuple[str, ...]
    permitted_write_paths: tuple[str, ...]
    network_policy: str
    approved_hosts: tuple[str, ...]
    max_runtime_seconds: int
    expected_result_schema_id: str
    expected_evidence: tuple[dict[str, Any], ...]
    redelegation_allowed: bool
    issued_at: str
    not_before: str
    expires_at: str
    artifact_hash: str

    def to_canonical_dict(self, *, include_hash: bool = True, include_id: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "issuer": self.issuer,
            "delegation_id": self.delegation_id,
            "delegated_task_hash": self.delegated_task_hash,
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "attempt_id": self.attempt_id,
            "attempt_hash": self.attempt_hash,
            "route_id": self.route_id,
            "route_hash": self.route_hash,
            "recipient_agent_id": self.recipient_agent_id,
            "worker_descriptor_hash": self.worker_descriptor_hash,
            "allowed_operation": self.allowed_operation,
            "allowed_tools": list(self.allowed_tools),
            "prohibited_tools": list(self.prohibited_tools),
            "permitted_read_paths": list(self.permitted_read_paths),
            "permitted_write_paths": list(self.permitted_write_paths),
            "network_policy": self.network_policy,
            "approved_hosts": list(self.approved_hosts),
            "max_runtime_seconds": self.max_runtime_seconds,
            "expected_result_schema_id": self.expected_result_schema_id,
            "expected_evidence": [dict(item) for item in self.expected_evidence],
            "redelegation_allowed": self.redelegation_allowed,
            "issued_at": self.issued_at,
            "not_before": self.not_before,
            "expires_at": self.expires_at,
        }
        if include_id:
            payload["lease_id"] = self.lease_id
        if include_hash:
            payload["artifact_hash"] = self.artifact_hash
        return payload

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> None:
        expected_id = f"lease-{sha256_payload(self.to_canonical_dict(include_hash=False, include_id=False))}"
        if expected_id != self.lease_id:
            raise DelegationIntegrityError("capability lease identity mismatch")
        if sha256_payload(self.to_canonical_dict(include_hash=False)) != self.artifact_hash:
            raise DelegationIntegrityError("capability lease artifact hash mismatch")


def build_delegated_capability_lease(
    *,
    delegation_id: str,
    delegated_task_hash: str,
    authorization_id: str,
    authorization_hash: str,
    attempt_id: str,
    attempt_hash: str,
    route_id: str,
    route_hash: str,
    recipient_agent_id: str,
    worker_descriptor_hash: str,
    allowed_operation: str,
    allowed_tools: Iterable[str],
    prohibited_tools: Iterable[str],
    permitted_read_paths: Iterable[str],
    permitted_write_paths: Iterable[str],
    network_policy: str,
    approved_hosts: Iterable[str],
    max_runtime_seconds: int,
    expected_result_schema_id: str,
    expected_evidence: Iterable[Mapping[str, Any]],
    issued_at: str,
    not_before: str,
    expires_at: str,
    redelegation_allowed: bool = False,
) -> DelegatedCapabilityLease:
    policy = _normalize_text(network_policy, "network_policy")
    hosts = _normalize_string_set(approved_hosts, "approved_hosts")
    if policy not in {"deny", "allowlist"}:
        raise InvalidCanonicalEnvelopeError("network_policy must be deny or allowlist")
    if policy == "deny" and hosts:
        raise InvalidCanonicalEnvelopeError("approved_hosts must be empty when network_policy is deny")
    allowed = _normalize_string_set(allowed_tools, "allowed_tools")
    prohibited = _normalize_string_set(prohibited_tools, "prohibited_tools")
    if set(allowed) & set(prohibited):
        raise InvalidCanonicalEnvelopeError("allowed_tools and prohibited_tools overlap")
    issued = _normalize_timestamp(issued_at, "issued_at")
    starts = _normalize_timestamp(not_before, "not_before")
    expires = _normalize_timestamp(expires_at, "expires_at")
    if not (_parse_timestamp(issued) <= _parse_timestamp(starts) < _parse_timestamp(expires)):
        raise InvalidCanonicalEnvelopeError("lease timestamps must satisfy issued_at <= not_before < expires_at")
    if redelegation_allowed is not False:
        raise InvalidCanonicalEnvelopeError("R12A capability leases prohibit redelegation")
    lease = DelegatedCapabilityLease(
        artifact_type=CAPABILITY_LEASE_ARTIFACT_TYPE,
        artifact_version=ARTIFACT_VERSION,
        lease_id="",
        issuer=LEASE_ISSUER,
        delegation_id=_normalize_text(delegation_id, "delegation_id"),
        delegated_task_hash=_normalize_hash(delegated_task_hash, "delegated_task_hash"),
        authorization_id=_normalize_text(authorization_id, "authorization_id"),
        authorization_hash=_normalize_hash(authorization_hash, "authorization_hash"),
        attempt_id=_normalize_text(attempt_id, "attempt_id"),
        attempt_hash=_normalize_hash(attempt_hash, "attempt_hash"),
        route_id=_normalize_text(route_id, "route_id"),
        route_hash=_normalize_hash(route_hash, "route_hash"),
        recipient_agent_id=_normalize_text(recipient_agent_id, "recipient_agent_id"),
        worker_descriptor_hash=_normalize_hash(worker_descriptor_hash, "worker_descriptor_hash"),
        allowed_operation=_normalize_text(allowed_operation, "allowed_operation"),
        allowed_tools=allowed,
        prohibited_tools=prohibited,
        permitted_read_paths=_normalize_string_set(permitted_read_paths, "permitted_read_paths", paths=True),
        permitted_write_paths=_normalize_string_set(permitted_write_paths, "permitted_write_paths", paths=True),
        network_policy=policy,
        approved_hosts=hosts,
        max_runtime_seconds=_normalize_int(max_runtime_seconds, "max_runtime_seconds", minimum=1),
        expected_result_schema_id=_normalize_text(expected_result_schema_id, "expected_result_schema_id"),
        expected_evidence=_normalize_ordered_records(expected_evidence, "expected_evidence"),
        redelegation_allowed=False,
        issued_at=issued,
        not_before=starts,
        expires_at=expires,
        artifact_hash="",
    )
    lease_id = f"lease-{sha256_payload(lease.to_canonical_dict(include_hash=False, include_id=False))}"
    lease = replace(lease, lease_id=lease_id)
    return replace(lease, artifact_hash=sha256_payload(lease.to_canonical_dict(include_hash=False)))


def reconstruct_capability_lease(payload: Mapping[str, Any]) -> DelegatedCapabilityLease:
    required = set(DelegatedCapabilityLease.__dataclass_fields__)
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise InvalidCanonicalEnvelopeError(f"capability lease requires exactly {sorted(required)}")
    if payload["artifact_type"] != CAPABILITY_LEASE_ARTIFACT_TYPE or payload["artifact_version"] != ARTIFACT_VERSION:
        raise InvalidCanonicalEnvelopeError("unsupported capability lease schema")
    if payload["issuer"] != LEASE_ISSUER:
        raise InvalidCanonicalEnvelopeError("unsupported capability lease issuer")
    rebuilt = build_delegated_capability_lease(
        delegation_id=payload["delegation_id"],
        delegated_task_hash=payload["delegated_task_hash"],
        authorization_id=payload["authorization_id"],
        authorization_hash=payload["authorization_hash"],
        attempt_id=payload["attempt_id"],
        attempt_hash=payload["attempt_hash"],
        route_id=payload["route_id"],
        route_hash=payload["route_hash"],
        recipient_agent_id=payload["recipient_agent_id"],
        worker_descriptor_hash=payload["worker_descriptor_hash"],
        allowed_operation=payload["allowed_operation"],
        allowed_tools=payload["allowed_tools"],
        prohibited_tools=payload["prohibited_tools"],
        permitted_read_paths=payload["permitted_read_paths"],
        permitted_write_paths=payload["permitted_write_paths"],
        network_policy=payload["network_policy"],
        approved_hosts=payload["approved_hosts"],
        max_runtime_seconds=payload["max_runtime_seconds"],
        expected_result_schema_id=payload["expected_result_schema_id"],
        expected_evidence=payload["expected_evidence"],
        issued_at=payload["issued_at"],
        not_before=payload["not_before"],
        expires_at=payload["expires_at"],
        redelegation_allowed=payload["redelegation_allowed"],
    )
    if payload["lease_id"] != rebuilt.lease_id or payload["artifact_hash"] != rebuilt.artifact_hash:
        raise DelegationIntegrityError("capability lease identity or artifact hash mismatch")
    return rebuilt


def validate_capability_request(
    lease: DelegatedCapabilityLease,
    *,
    recipient_agent_id: str,
    delegation_id: str,
    operation: str,
    tools: Iterable[str] = (),
    read_paths: Iterable[str] = (),
    write_paths: Iterable[str] = (),
    network_hosts: Iterable[str] = (),
    at: str,
) -> None:
    lease.verify_hash()
    if recipient_agent_id != lease.recipient_agent_id:
        raise CapabilityViolationError("wrong capability-lease recipient")
    if delegation_id != lease.delegation_id:
        raise CapabilityViolationError("wrong capability-lease delegation")
    if operation != lease.allowed_operation:
        raise CapabilityViolationError("operation is outside the capability lease")
    requested_tools = set(_normalize_string_set(tools, "tools"))
    if not requested_tools.issubset(lease.allowed_tools):
        raise CapabilityViolationError("requested tools exceed the capability lease")
    if requested_tools & set(lease.prohibited_tools):
        raise CapabilityViolationError("requested tool is explicitly prohibited")
    if not set(_normalize_string_set(read_paths, "read_paths", paths=True)).issubset(lease.permitted_read_paths):
        raise CapabilityViolationError("requested read path exceeds the capability lease")
    if not set(_normalize_string_set(write_paths, "write_paths", paths=True)).issubset(lease.permitted_write_paths):
        raise CapabilityViolationError("requested write path exceeds the capability lease")
    requested_hosts = set(_normalize_string_set(network_hosts, "network_hosts"))
    if lease.network_policy == "deny" and requested_hosts:
        raise CapabilityViolationError("network use is prohibited")
    if not requested_hosts.issubset(lease.approved_hosts):
        raise CapabilityViolationError("requested network host exceeds the capability lease")
    timestamp = _normalize_timestamp(at, "at")
    if _parse_timestamp(timestamp) < _parse_timestamp(lease.not_before):
        raise CapabilityViolationError("capability lease is not active yet")
    if _parse_timestamp(timestamp) >= _parse_timestamp(lease.expires_at):
        raise LeaseExpiredError("capability lease is expired")
