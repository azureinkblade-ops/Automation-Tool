"""EA-4E.28 external invocation-authorization issuer.

The governed runtime consumes invocation authorization but may not create it.
This module issues one bounded EA-4E.23 artifact for an explicitly identified
request and an already-resolved EA-4E.22 binding. It has no execution or I/O
capability.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import timedelta

from tools.hermes_core.governed_bound_executor import (
    GovernedExecutorResolution,
    compute_ea4e22_integration_contract_id,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    QUALIFIED_RECEIVERS,
    parse_iso_timestamp,
    compute_ea4e21_binding_contract_id,
)
from tools.hermes_core.production_invocation_authorization import (
    MAX_AUTHORIZED_ATTEMPTS,
    MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS,
    ProductionInvocationAuthorization,
    compute_ea4e23_invocation_contract_id,
)


ISSUER_SCHEMA_ID = "hermes.production-invocation-authorization-issuer/v1"
ISSUER_SCHEMA_VERSION = "ea4e.28"
ISSUER_ARTIFACT_VERSION = "1"


@dataclass(frozen=True)
class ProductionInvocationAuthorizationIssueRequest:
    issue_request_id: str
    execution_request_id: str
    receiver_id: str
    binding_id: str
    enablement_id: str
    nonce: str
    requested_ttl_seconds: int = MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS
    attempt_number: int = MAX_AUTHORIZED_ATTEMPTS
    runtime_scope: str = "production"
    delegation_class: str = "governed"

    def to_canonical_dict(self) -> dict:
        return {
            "issue_request_id": self.issue_request_id,
            "execution_request_id": self.execution_request_id,
            "receiver_id": self.receiver_id,
            "binding_id": self.binding_id,
            "enablement_id": self.enablement_id,
            "nonce": self.nonce,
            "requested_ttl_seconds": self.requested_ttl_seconds,
            "attempt_number": self.attempt_number,
            "runtime_scope": self.runtime_scope,
            "delegation_class": self.delegation_class,
        }


@dataclass(frozen=True)
class ProductionInvocationAuthorizationIssueResult:
    policy_decision: str
    policy_reason: str
    authorization: ProductionInvocationAuthorization | None = None
    idempotent_replay: bool = False


class ProductionInvocationAuthorizationIssuer:
    """Issue bounded authorization without routing, binding, or execution."""

    def __init__(self, *, clock: BindingClock) -> None:
        self._clock = clock
        self._issued: dict[
            str, tuple[str, ProductionInvocationAuthorization]
        ] = {}
        self._lock = threading.RLock()

    def issue(
        self,
        request: ProductionInvocationAuthorizationIssueRequest,
        resolution: GovernedExecutorResolution,
    ) -> ProductionInvocationAuthorizationIssueResult:
        request_hash = sha256_payload(request.to_canonical_dict())
        with self._lock:
            existing = self._issued.get(request.issue_request_id)
            if existing is not None and existing[0] != request_hash:
                return self._deny("ISSUE_REQUEST_ID_COLLISION")

            reason = self._validate(request, resolution)
            if reason is not None:
                return self._deny(reason)

            if existing is not None:
                _, authorization = existing
                return ProductionInvocationAuthorizationIssueResult(
                    policy_decision="ALLOW",
                    policy_reason="IDEMPOTENT_ISSUANCE_REPLAY",
                    authorization=authorization,
                    idempotent_replay=True,
                )

            issued_at = parse_iso_timestamp(self._clock.now_iso())
            expires_at = issued_at + timedelta(seconds=request.requested_ttl_seconds)
            authorization_id = "ea4e28-" + sha256_payload({
                "issue_request": request.to_canonical_dict(),
                "issued_at": issued_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            })
            authorization = ProductionInvocationAuthorization(
                invocation_authorization_id=authorization_id,
                receiver_id=request.receiver_id,
                binding_id=request.binding_id,
                enablement_id=request.enablement_id,
                execution_request_id=request.execution_request_id,
                attempt_number=request.attempt_number,
                issued_at=issued_at.isoformat(),
                expires_at=expires_at.isoformat(),
                runtime_scope=request.runtime_scope,
                delegation_class=request.delegation_class,
                nonce=request.nonce,
            )
            self._issued[request.issue_request_id] = (request_hash, authorization)
            return ProductionInvocationAuthorizationIssueResult(
                policy_decision="ALLOW",
                policy_reason="INVOCATION_AUTHORIZATION_ISSUED",
                authorization=authorization,
            )

    def _validate(
        self,
        request: ProductionInvocationAuthorizationIssueRequest,
        resolution: GovernedExecutorResolution,
    ) -> str | None:
        required = {
            "issue_request_id": request.issue_request_id,
            "execution_request_id": request.execution_request_id,
            "receiver_id": request.receiver_id,
            "binding_id": request.binding_id,
            "enablement_id": request.enablement_id,
            "nonce": request.nonce,
        }
        if any(not isinstance(value, str) or not value.strip() for value in required.values()):
            return "REQUIRED_IDENTITY_MISSING"
        if request.receiver_id not in QUALIFIED_RECEIVERS:
            return "UNSUPPORTED_RECEIVER"
        if resolution.resolution_decision != "RESOLVED":
            return "BOUND_EXECUTOR_NOT_RESOLVED"
        handle = resolution.binding_handle
        if handle is None:
            return "BINDING_HANDLE_MISSING"
        if resolution.executor is None:
            return "RESOLVED_EXECUTOR_MISSING"
        if request.receiver_id != resolution.receiver_id or request.receiver_id != handle.receiver_id:
            return "RECEIVER_RESOLUTION_MISMATCH"
        if request.binding_id != resolution.binding_id or request.binding_id != handle.binding_id:
            return "BINDING_ID_MISMATCH"
        if request.enablement_id != handle.enablement_id:
            return "ENABLEMENT_ID_MISMATCH"
        if request.attempt_number != MAX_AUTHORIZED_ATTEMPTS:
            return "INVALID_ATTEMPT_NUMBER"
        if not 1 <= request.requested_ttl_seconds <= MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS:
            return "INVALID_AUTHORIZATION_TTL"
        if request.runtime_scope != "production":
            return "UNSUPPORTED_RUNTIME_SCOPE"
        if request.delegation_class != "governed":
            return "UNSUPPORTED_DELEGATION_CLASS"
        try:
            now = parse_iso_timestamp(self._clock.now_iso())
            binding_expiry = parse_iso_timestamp(handle.expires_at)
        except ValueError:
            return "INVALID_TIMESTAMP"
        if binding_expiry <= now:
            return "BINDING_EXPIRED"
        if now + timedelta(seconds=request.requested_ttl_seconds) > binding_expiry:
            return "AUTHORIZATION_OUTLIVES_BINDING"
        return None

    @staticmethod
    def _deny(reason: str) -> ProductionInvocationAuthorizationIssueResult:
        return ProductionInvocationAuthorizationIssueResult(
            policy_decision="DENY",
            policy_reason=reason,
        )


def compute_ea4e28_issuer_contract_id() -> str:
    canonical = {
        "schema_id": ISSUER_SCHEMA_ID,
        "schema_version": ISSUER_SCHEMA_VERSION,
        "artifact_version": ISSUER_ARTIFACT_VERSION,
        "ea4e21_binding_contract_id": compute_ea4e21_binding_contract_id(),
        "ea4e22_integration_contract_id": compute_ea4e22_integration_contract_id(),
        "ea4e23_invocation_contract_id": compute_ea4e23_invocation_contract_id(),
        "runtime_is_not_issuer": True,
        "explicit_issue_request_required": True,
        "resolved_binding_required": True,
        "exact_receiver_binding_enablement_identity": True,
        "execution_request_identity_bound": True,
        "authorization_may_not_outlive_binding": True,
        "max_ttl_seconds": MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS,
        "max_attempts": MAX_AUTHORIZED_ATTEMPTS,
        "identical_replay": "RETURN_EXISTING",
        "same_id_conflict": "DENY",
        "replay_revalidates_resolution": True,
        "authorization_id_binds_issuance_window": True,
        "qualified_receiver_required": True,
        "default_decision": "DENY",
        "routing_capability": False,
        "binding_capability": False,
        "execution_capability": False,
        "io_capability": False,
    }
    return sha256_payload(canonical)
