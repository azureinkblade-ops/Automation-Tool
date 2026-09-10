"""Explicit, non-executing production-activation authorization contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable, Mapping

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_activation import (
    ProductionActivation,
    ProductionActivationValidator,
)
from tools.hermes_core.production_activation_authorization_store import (
    ProductionActivationAuthorizationStore,
    ProductionActivationAuthorizationStoreError,
)
from tools.hermes_core.production_issuance import ClockCollaborator, QUALIFIED_RECEIVERS
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


ACTIVATION_AUTHORIZATION_SCHEMA_ID = "hermes.production-activation-authorization/v1"
ACTIVATION_AUTHORIZATION_VERSION = "ea4e.59"
ACTIVATION_AUTHORIZATION_ARTIFACT_VERSION = "1"
ACTIVATION_AUTHORIZATION_DEFAULT_TTL = 300
ACTIVATION_AUTHORIZATION_MAX_TTL = 300
AUTHORIZED = "AUTHORIZED"
DENIED = "DENIED"

FAILURE_CODES = frozenset(
    {
        "REQUEST_MISSING", "MALFORMED_REQUEST", "OPERATOR_INTENT_MISSING",
        "READINESS_NOT_PASS", "UNQUALIFIED_RECEIVER", "FEATURE_GATE_DISABLED",
        "COMMIT_MISMATCH", "ROUTER_CONTRACT_MISMATCH",
        "AUTHORITY_CONTRACT_MISMATCH", "TRANSPORT_BINDING_MISMATCH",
        "MODEL_BINDING_MISMATCH", "EXPIRED", "REPLAY", "RECOVERY_BLOCKED",
        "CONFLICTING_OUTSTANDING_AUTH", "MISSING_BINDING",
        "EXECUTION_AUTHORITY_INVALID", "CLAIM_FAILED", "TRANSITION_FAILED",
        "CONSUME_PERSISTENCE_FAILED", "UNSUPPORTED_RECEIVER",
        "ACTIVATION_AUTHORIZATION_MISSING", "REQUEST_ID_MISMATCH",
        "RECEIVER_MISMATCH", "ACTIVATION_AUTH_STORE_UNAVAILABLE",
        "INVALID_ACTIVATION_AUTH_TIME", "TRANSITION_REQUIRES_CLAIMED_AUTHORIZATION",
    }
)


@dataclass(frozen=True)
class ProductionActivationAuthorizationRequest:
    request_id: str
    receiver_id: str
    governing_commit: str
    router_contract_id: str
    authority_contract_id: str
    transport_contract_id: str
    model_binding_id: str
    feature_gate_state: str
    activation_mode: str
    operator_intent: str
    nonce: str
    requested_ttl_seconds: int = ACTIVATION_AUTHORIZATION_DEFAULT_TTL


@dataclass(frozen=True)
class ProductionActivationAuthorization:
    activation_authorization_id: str
    schema_id: str
    artifact_version: str
    request_id: str
    receiver_id: str
    governing_commit: str
    router_contract_id: str
    authority_contract_id: str
    transport_contract_id: str
    model_binding_id: str
    feature_gate_state: str
    activation_mode: str
    decision: str
    issuer_id: str
    issued_at: str
    expires_at: str
    nonce: str
    artifact_hash: str

    def canonical_fields(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "artifact_version": self.artifact_version,
            "request_id": self.request_id,
            "receiver_id": self.receiver_id,
            "governing_commit": self.governing_commit,
            "router_contract_id": self.router_contract_id,
            "authority_contract_id": self.authority_contract_id,
            "transport_contract_id": self.transport_contract_id,
            "model_binding_id": self.model_binding_id,
            "feature_gate_state": self.feature_gate_state,
            "activation_mode": self.activation_mode,
            "decision": self.decision,
            "issuer_id": self.issuer_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    def verify_hash(self) -> bool:
        return (
            sha256_payload(self.canonical_fields()) == self.artifact_hash
            and self.activation_authorization_id
            == f"production-activation-auth-{self.artifact_hash[:16]}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_authorization_id": self.activation_authorization_id,
            **self.canonical_fields(),
            "artifact_hash": self.artifact_hash,
        }


@dataclass(frozen=True)
class ProductionActivationAuthorizationIssueResult:
    decision: str
    reason: str
    artifact: ProductionActivationAuthorization | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "authorization": None if self.artifact is None else self.artifact.to_dict(),
        }


@dataclass(frozen=True)
class ProductionActivationAuthorizationValidationResult:
    valid: bool
    reason: str


@dataclass(frozen=True)
class ProductionActivationAuthorizationClaimResult:
    decision: str
    reason: str
    artifact: ProductionActivationAuthorization | None = None
    state: str = "DENIED"


@dataclass(frozen=True)
class ProductionActivationTransitionResult:
    decision: str
    reason: str
    request_activation_state: str
    durable_authorization_state: str
    recovery_required: bool = False


class ProductionActivationAuthorizationPolicy:
    """Deterministic issuance policy and sole request-path Store.claim caller."""

    def __init__(
        self,
        *,
        store: ProductionActivationAuthorizationStore,
        clock: ClockCollaborator,
        governing_commit: str,
        readiness_status: str,
        recovery_blocked: bool | Callable[[], bool] = False,
    ) -> None:
        self.store = store
        self.clock = clock
        self.governing_commit = governing_commit
        self.readiness_status = readiness_status
        self.recovery_blocked = recovery_blocked

    def evaluate(self, request: ProductionActivationAuthorizationRequest | None) -> tuple[str, str]:
        if request is None:
            return DENIED, "REQUEST_MISSING"
        required = (
            request.request_id, request.receiver_id, request.governing_commit,
            request.router_contract_id, request.authority_contract_id,
            request.transport_contract_id, request.model_binding_id,
            request.feature_gate_state, request.activation_mode, request.operator_intent,
            request.nonce,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            return DENIED, "MALFORMED_REQUEST"
        if request.operator_intent != "EXPLICIT":
            return DENIED, "OPERATOR_INTENT_MISSING"
        if self.readiness_status != "PASS":
            return DENIED, "READINESS_NOT_PASS"
        if request.receiver_id not in QUALIFIED_RECEIVERS:
            return DENIED, "UNSUPPORTED_RECEIVER"
        if request.feature_gate_state != "ENABLED":
            return DENIED, "FEATURE_GATE_DISABLED"
        if request.activation_mode != "ENABLED":
            return DENIED, "MALFORMED_REQUEST"
        if request.governing_commit != self.governing_commit:
            return DENIED, "COMMIT_MISMATCH"
        if request.router_contract_id != compute_ea4e6_router_contract_id():
            return DENIED, "ROUTER_CONTRACT_MISMATCH"
        if request.authority_contract_id != compute_ea4e7_authority_contract_id():
            return DENIED, "AUTHORITY_CONTRACT_MISMATCH"
        expected = QUALIFIED_RECEIVERS[request.receiver_id]
        if request.transport_contract_id != expected["transport_contract_id"]:
            return DENIED, "TRANSPORT_BINDING_MISMATCH"
        if request.model_binding_id != expected["model_binding_id"]:
            return DENIED, "MODEL_BINDING_MISMATCH"
        try:
            recovery_blocked = (
                self.recovery_blocked()
                if callable(self.recovery_blocked)
                else self.recovery_blocked
            )
        except Exception:
            return DENIED, "RECOVERY_BLOCKED"
        if recovery_blocked:
            return DENIED, "RECOVERY_BLOCKED"
        if type(request.requested_ttl_seconds) is not int or not (
            0 < request.requested_ttl_seconds <= ACTIVATION_AUTHORIZATION_MAX_TTL
        ):
            return DENIED, "MALFORMED_REQUEST"
        if self.store.has_outstanding():
            return DENIED, "CONFLICTING_OUTSTANDING_AUTH"
        return AUTHORIZED, "ACTIVATION_AUTHORIZATION_POLICY_ALLOWED"

    def claim(
        self,
        artifact: ProductionActivationAuthorization | None,
        *,
        validator: "ProductionActivationAuthorizationValidator",
        request_id: str,
        receiver_id: str,
        feature_gate_state: str,
    ) -> ProductionActivationAuthorizationClaimResult:
        validation = validator.validate(
            artifact,
            request_id=request_id,
            receiver_id=receiver_id,
            governing_commit=self.governing_commit,
            feature_gate_state=feature_gate_state,
        )
        if not validation.valid or artifact is None:
            return ProductionActivationAuthorizationClaimResult(DENIED, validation.reason)
        try:
            state = self.store.claim(artifact.activation_authorization_id, self.clock.now_iso())
        except ProductionActivationAuthorizationStoreError as exc:
            return ProductionActivationAuthorizationClaimResult(DENIED, exc.reason)
        return ProductionActivationAuthorizationClaimResult(
            AUTHORIZED, "ACTIVATION_AUTHORIZATION_CLAIMED", artifact, state
        )


class ProductionActivationAuthorizationIssuer:
    """Dedicated issue-only collaborator. Issuance stops at durable ISSUED."""

    ISSUER_ID = "hermes-production-activation-authorization-issuer"

    def __init__(self, policy: ProductionActivationAuthorizationPolicy) -> None:
        self._policy = policy

    def issue(
        self, request: ProductionActivationAuthorizationRequest | None
    ) -> ProductionActivationAuthorizationIssueResult:
        try:
            now = self._policy.clock.now_iso()
        except Exception:
            return ProductionActivationAuthorizationIssueResult(
                DENIED, "INVALID_ACTIVATION_AUTH_TIME"
            )
        try:
            if request is not None:
                self._policy.store.expire_outstanding(now)
            decision, reason = self._policy.evaluate(request)
        except ProductionActivationAuthorizationStoreError as exc:
            return ProductionActivationAuthorizationIssueResult(DENIED, exc.reason)
        except Exception:
            return ProductionActivationAuthorizationIssueResult(
                DENIED, "ACTIVATION_AUTH_STORE_UNAVAILABLE"
            )
        if decision != AUTHORIZED or request is None:
            if request is not None:
                try:
                    self._policy.store.record_denied(request, now, reason)
                except Exception:
                    pass
            return ProductionActivationAuthorizationIssueResult(DENIED, reason)
        try:
            issued = _parse_time(now)
        except (TypeError, ValueError):
            return ProductionActivationAuthorizationIssueResult(
                DENIED, "INVALID_ACTIVATION_AUTH_TIME"
            )
        expires = issued + timedelta(seconds=request.requested_ttl_seconds)
        artifact = build_production_activation_authorization(
            request=request,
            issuer_id=self.ISSUER_ID,
            issued_at=issued.isoformat(),
            expires_at=expires.isoformat(),
        )
        try:
            self._policy.store.persist_issued(artifact, now)
        except ProductionActivationAuthorizationStoreError as exc:
            return ProductionActivationAuthorizationIssueResult(DENIED, exc.reason)
        return ProductionActivationAuthorizationIssueResult(
            AUTHORIZED, "ACTIVATION_AUTHORIZATION_ISSUED", artifact
        )


class ProductionActivationAuthorizationValidator:
    """Non-mutating artifact and durable-eligibility validator."""

    def __init__(
        self,
        *,
        store: ProductionActivationAuthorizationStore,
        clock: ClockCollaborator,
    ) -> None:
        self._store = store
        self._clock = clock

    def validate(
        self,
        artifact: ProductionActivationAuthorization | None,
        *,
        request_id: str,
        receiver_id: str,
        governing_commit: str,
        feature_gate_state: str,
    ) -> ProductionActivationAuthorizationValidationResult:
        if artifact is None:
            return self._deny("ACTIVATION_AUTHORIZATION_MISSING")
        if artifact.schema_id != ACTIVATION_AUTHORIZATION_SCHEMA_ID:
            return self._deny("MALFORMED_REQUEST")
        if artifact.artifact_version != ACTIVATION_AUTHORIZATION_ARTIFACT_VERSION:
            return self._deny("MALFORMED_REQUEST")
        if (
            artifact.decision != AUTHORIZED
            or artifact.issuer_id != ProductionActivationAuthorizationIssuer.ISSUER_ID
            or not artifact.verify_hash()
        ):
            return self._deny("MALFORMED_REQUEST")
        expected = QUALIFIED_RECEIVERS.get(receiver_id)
        checks = (
            (artifact.request_id == request_id, "REQUEST_ID_MISMATCH"),
            (artifact.receiver_id == receiver_id, "RECEIVER_MISMATCH"),
            (artifact.governing_commit == governing_commit, "COMMIT_MISMATCH"),
            (artifact.router_contract_id == compute_ea4e6_router_contract_id(), "ROUTER_CONTRACT_MISMATCH"),
            (artifact.authority_contract_id == compute_ea4e7_authority_contract_id(), "AUTHORITY_CONTRACT_MISMATCH"),
            (expected is not None, "UNSUPPORTED_RECEIVER"),
            (expected is not None and artifact.transport_contract_id == expected["transport_contract_id"], "TRANSPORT_BINDING_MISMATCH"),
            (expected is not None and artifact.model_binding_id == expected["model_binding_id"], "MODEL_BINDING_MISMATCH"),
            (artifact.feature_gate_state == feature_gate_state == "ENABLED", "FEATURE_GATE_DISABLED"),
            (artifact.activation_mode == "ENABLED", "MALFORMED_REQUEST"),
            (bool(artifact.nonce), "MALFORMED_REQUEST"),
        )
        for allowed, reason in checks:
            if not allowed:
                return self._deny(reason)
        try:
            now = _parse_time(self._clock.now_iso())
            issued = _parse_time(artifact.issued_at)
            expires = _parse_time(artifact.expires_at)
            if issued > now or expires <= issued:
                return self._deny("MALFORMED_REQUEST")
            if (expires - issued).total_seconds() > ACTIVATION_AUTHORIZATION_MAX_TTL:
                return self._deny("MALFORMED_REQUEST")
            if now >= expires:
                return self._deny("EXPIRED")
            if self._store.state(artifact.activation_authorization_id) != "ISSUED":
                return self._deny("REPLAY")
            stored = self._store.load_artifact(artifact.activation_authorization_id)
            if stored != artifact.to_dict():
                return self._deny("MALFORMED_REQUEST")
        except ProductionActivationAuthorizationStoreError as exc:
            return self._deny(exc.reason)
        except (ValueError, TypeError):
            return self._deny("MALFORMED_REQUEST")
        return ProductionActivationAuthorizationValidationResult(True, "ACTIVATION_AUTHORIZATION_VALID")

    @staticmethod
    def _deny(reason: str) -> ProductionActivationAuthorizationValidationResult:
        return ProductionActivationAuthorizationValidationResult(False, reason)


class ProductionAppActivationTransitionOwner:
    """Own request-scoped activation transition, durable consume, and teardown."""

    def __init__(
        self,
        *,
        store: ProductionActivationAuthorizationStore,
        clock: ClockCollaborator,
        activation_validator: ProductionActivationValidator,
        recovery_marker: Callable[[str], None] | None = None,
        consume_failure_recovery_marker: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._activation_validator = activation_validator
        self._recovery_marker = recovery_marker
        self._consume_failure_recovery_marker = consume_failure_recovery_marker
        self._active: dict[str, ProductionActivationAuthorization] = {}
        self._lock = Lock()

    def transition(
        self,
        *,
        request_id: str,
        receiver_id: str,
        claimed_authorization: ProductionActivationAuthorizationClaimResult,
        production_activation: ProductionActivation | None,
    ) -> ProductionActivationTransitionResult:
        artifact = claimed_authorization.artifact
        if (
            claimed_authorization.decision != AUTHORIZED
            or claimed_authorization.state != "CLAIMED"
            or artifact is None
            or self._store.state(artifact.activation_authorization_id) != "CLAIMED"
        ):
            return self._deny("TRANSITION_REQUIRES_CLAIMED_AUTHORIZATION")
        activation_result = self._activation_validator.validate(
            production_activation, receiver_id=receiver_id
        )
        if not activation_result.activation_valid:
            try:
                self._store.abort(artifact.activation_authorization_id, self._clock.now_iso())
            except ProductionActivationAuthorizationStoreError:
                self._mark_recovery(request_id)
                return self._recovery("TRANSITION_FAILED_ABORT_UNCONFIRMED")
            return ProductionActivationTransitionResult(
                DENIED, "TRANSITION_FAILED", "DISABLED", "ABORTED"
            )
        with self._lock:
            self._active[request_id] = artifact
        try:
            self._store.record_activation_event(
                artifact, "PRODUCTION_ACTIVATION_ENTERED", self._clock.now_iso()
            )
        except ProductionActivationAuthorizationStoreError:
            pass
        try:
            self._store.consume(artifact.activation_authorization_id, self._clock.now_iso())
        except ProductionActivationAuthorizationStoreError:
            with self._lock:
                self._active.pop(request_id, None)
            marker_persisted = self._mark_consume_failure_recovery(
                request_id, artifact.activation_authorization_id
            )
            if not marker_persisted:
                return self._recovery(
                    "CONSUME_PERSISTENCE_AND_RECOVERY_MARKER_FAILED"
                )
            return self._recovery("CONSUME_PERSISTENCE_FAILED")
        retained_validation = self._activation_validator.validate(
            production_activation, receiver_id=receiver_id
        )
        if not retained_validation.activation_valid:
            self._mark_recovery(request_id)
            return self._recovery("POST_CONSUME_ACTIVATION_VALIDATION_FAILED")
        return ProductionActivationTransitionResult(
            AUTHORIZED,
            "PRODUCTION_ACTIVATION_ENTERED",
            "ACTIVATED_FOR_REQUEST",
            "CONSUMED",
        )

    def teardown(self, request_id: str) -> bool:
        with self._lock:
            artifact = self._active.pop(request_id, None)
        if artifact is None:
            return True
        try:
            self._store.record_activation_event(
                artifact, "PRODUCTION_ACTIVATION_EXITED", self._clock.now_iso()
            )
        except Exception:
            pass
        return True

    def is_active(self, request_id: str) -> bool:
        with self._lock:
            return request_id in self._active

    def _mark_recovery(self, request_id: str) -> None:
        if self._recovery_marker is not None:
            self._recovery_marker(request_id)

    def _mark_consume_failure_recovery(
        self, request_id: str, activation_authorization_id: str
    ) -> bool:
        try:
            if self._consume_failure_recovery_marker is not None:
                self._consume_failure_recovery_marker(
                    request_id,
                    activation_authorization_id,
                    "ACTIVATION_AUTH_CONSUME_PERSISTENCE_UNCERTAIN",
                )
            elif self._recovery_marker is not None:
                self._recovery_marker(request_id)
            return True
        except Exception:
            return False

    @staticmethod
    def _deny(reason: str) -> ProductionActivationTransitionResult:
        return ProductionActivationTransitionResult(DENIED, reason, "DISABLED", "DENIED")

    @staticmethod
    def _recovery(reason: str) -> ProductionActivationTransitionResult:
        return ProductionActivationTransitionResult(
            DENIED, reason, "DISABLED", "RECOVERY_REQUIRED_TO_CONFIRM_ABORTED", True
        )


def build_production_activation_authorization(
    *,
    request: ProductionActivationAuthorizationRequest,
    issuer_id: str,
    issued_at: str,
    expires_at: str,
) -> ProductionActivationAuthorization:
    fields = {
        "schema_id": ACTIVATION_AUTHORIZATION_SCHEMA_ID,
        "artifact_version": ACTIVATION_AUTHORIZATION_ARTIFACT_VERSION,
        "request_id": request.request_id,
        "receiver_id": request.receiver_id,
        "governing_commit": request.governing_commit,
        "router_contract_id": request.router_contract_id,
        "authority_contract_id": request.authority_contract_id,
        "transport_contract_id": request.transport_contract_id,
        "model_binding_id": request.model_binding_id,
        "feature_gate_state": request.feature_gate_state,
        "activation_mode": request.activation_mode,
        "decision": AUTHORIZED,
        "issuer_id": issuer_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": request.nonce,
    }
    artifact_hash = sha256_payload(fields)
    return ProductionActivationAuthorization(
        activation_authorization_id=f"production-activation-auth-{artifact_hash[:16]}",
        artifact_hash=artifact_hash,
        **fields,
    )


def activation_authorization_from_mapping(
    value: object,
) -> ProductionActivationAuthorization | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("activation authorization must be a mapping")
    return ProductionActivationAuthorization(
        **{
            name: value[name]
            for name in ProductionActivationAuthorization.__dataclass_fields__
        }
    )


def activation_authorization_request_from_mapping(
    value: object,
) -> ProductionActivationAuthorizationRequest | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("activation authorization request must be a mapping")
    return ProductionActivationAuthorizationRequest(
        **{
            name: value[name]
            for name in ProductionActivationAuthorizationRequest.__dataclass_fields__
            if name in value
        }
    )


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("activation authorization time must be timezone-aware")
    return parsed
