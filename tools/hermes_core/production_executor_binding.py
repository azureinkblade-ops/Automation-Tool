"""EA-4E.21 production real-executor binding policy / runtime enablement control.

This module establishes the permanent runtime-control layer between:
- qualified real executor implementation
and:
- production ExecutorRegistry registration.

The policy answers: MAY THIS QUALIFIED REAL EXECUTOR BE BOUND INTO THIS RUNTIME REGISTRY NOW?

It does NOT answer: WHICH RECEIVER SHOULD BE SELECTED?
It does NOT issue execution authority.
It does NOT issue production activation.
It does NOT execute a receiver.
It does NOT create fallback or retry behavior.

Core invariants:
    ROUTING != ISSUANCE != AUTHORIZATION != ACTIVATION != BINDING != EXECUTION

Target architecture:
    Explicit runtime enablement request
    -> binding policy validation
    -> qualified receiver validation
    -> transport contract validation
    -> model binding validation
    -> required upstream contract validation
    -> bounded runtime scope validation
    -> binding authorization result
    -> explicit registry binding
    -> bounded lifetime
    -> explicit teardown
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.production_issuance import (
    ALLOWED_DELEGATION_CLASS,
    QUALIFIED_RECEIVERS,
    compute_ea4e17_issuance_contract_id,
)
from tools.hermes_core.governed_production import compute_ea4e18_integration_contract_id


# --------------------------------------------------------------------------- #
# Deterministic timestamp parsing and TTL canonicalization
# --------------------------------------------------------------------------- #

def parse_iso_timestamp(value: str) -> datetime:
    """Parse ISO 8601 timestamp deterministically.

    Requires timezone-aware timestamps.
    Rejects malformed and naive (timezone-unaware) timestamps.
    Normalizes to UTC internally.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Malformed timestamp: {value!r}")

    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Malformed timestamp: {value!r}") from e

    if dt.tzinfo is None:
        raise ValueError(f"Timezone-required: {value!r} is naive")

    # Normalize to UTC for deterministic comparison
    return dt.astimezone(timezone.utc)


def parse_requested_ttl(value: Any) -> Decimal:
    """Parse requested TTL into exact Decimal representation.

    Supports int, float, str, Decimal.
    Rejects NaN, Infinity, negative values.
    """
    if isinstance(value, Decimal):
        ttl = value
    elif isinstance(value, int):
        ttl = Decimal(value)
    elif isinstance(value, float):
        # Convert float to string first to avoid binary float artifacts
        ttl = Decimal(str(value))
    elif isinstance(value, str):
        ttl = Decimal(value.strip())
    else:
        raise ValueError(f"Invalid TTL type: {type(value)}")

    if ttl.is_nan() or ttl.is_infinite():
        raise ValueError(f"Invalid TTL: {value}")
    if ttl <= 0:
        raise ValueError(f"TTL must be positive: {value}")

    return ttl


def ttl_to_canonical_str(ttl: Decimal) -> str:
    """Canonicalize TTL to normalized decimal string.

    3600, 3600.0, 3600.000000 all canonicalize to "3600".
    0.5 stays "0.5".
    """
    # Normalize removes trailing zeros
    normalized = ttl.normalize()
    # If it's an integer after normalization, return as integer string
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return str(normalized)


# --------------------------------------------------------------------------- #
# Binding schema
# --------------------------------------------------------------------------- #

BINDING_SCHEMA_ID = "hermes.production-executor-binding.receiver-dispatch/v1"
BINDING_SCHEMA_VERSION = "ea4e.21"
BINDING_ARTIFACT_VERSION = "1"

# Policy constants
DEFAULT_BINDING_DECISION = "DENY"
ALLOWED_RUNTIME_SCOPE = "production"
MAX_BINDING_TTL_SECONDS = 3600  # 1 hour - POLICY MAXIMUM
MAX_SIMULTANEOUS_REAL_BINDINGS = 1


# --------------------------------------------------------------------------- #
# Executor implementation registry
# --------------------------------------------------------------------------- #

QUALIFIED_EXECUTOR_IMPLEMENTATIONS: dict[str, dict[str, str]] = {
    "kilo-cli-agent": {
        "executor_identity": "RealKiloProductionExecutor",
        "executor_factory": "tools.hermes_core.kilo_live_binding:RealKiloProductionExecutor",
        "transport_contract_id": QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        "model_binding_id": QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
    },
    "opencode-cli-agent": {
        "executor_identity": "RealOpenCodeProductionExecutor",
        "executor_factory": "tools.hermes_core.opencode_live_binding:RealOpenCodeProductionExecutor",
        "transport_contract_id": "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f",
        "model_binding_id": "cfcf7353842b923579db1676484bba6d0cba77927bdd592439898dde71773371",
    },
}


# --------------------------------------------------------------------------- #
# Clock collaborator for deterministic time
# --------------------------------------------------------------------------- #

class BindingClock:
    """Injected clock for deterministic binding TTL computation."""

    def __init__(self, *, now: str) -> None:
        self._now = now

    def now_iso(self) -> str:
        return self._now

    def now_plus_seconds(self, seconds: int) -> str:
        """Compute expiry time from injected now."""
        base = datetime.fromisoformat(self._now)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        expiry = base + timedelta(seconds=seconds)
        return expiry.isoformat()


# --------------------------------------------------------------------------- #
# Binding enablement artifact
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionExecutorBindingEnablement:
    """Explicit runtime enablement request for real-executor binding.

    Distinct from ProductionActivation: this authorizes registration of
    a real executor implementation, not execution scope.
    """
    enablement_id: str
    receiver_id: str
    transport_contract_id: str
    model_binding_id: str
    executor_identity: str
    executor_factory: str
    runtime_scope: str
    issued_at: str
    expires_at: str
    delegation_class: str = ALLOWED_DELEGATION_CLASS
    requested_ttl_seconds: Decimal = Decimal("3600")
    max_bound_executors: int = MAX_SIMULTANEOUS_REAL_BINDINGS
    enabled: bool = True
    request_nonce: str = ""

    def __post_init__(self) -> None:
        """Ensure requested_ttl_seconds is Decimal."""
        if not isinstance(self.requested_ttl_seconds, Decimal):
            object.__setattr__(self, "requested_ttl_seconds", Decimal(str(self.requested_ttl_seconds)))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "enablement_id": self.enablement_id,
            "receiver_id": self.receiver_id,
            "transport_contract_id": self.transport_contract_id,
            "model_binding_id": self.model_binding_id,
            "executor_identity": self.executor_identity,
            "executor_factory": self.executor_factory,
            "runtime_scope": self.runtime_scope,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "delegation_class": self.delegation_class,
            "requested_ttl_seconds": ttl_to_canonical_str(self.requested_ttl_seconds),
            "max_bound_executors": self.max_bound_executors,
            "enabled": self.enabled,
            "request_nonce": self.request_nonce,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())


# --------------------------------------------------------------------------- #
# Binding handle
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionExecutorBindingHandle:
    """Handle representing a successful binding operation."""
    binding_id: str
    enablement_id: str
    receiver_id: str
    executor_identity: str
    bound_at: str
    expires_at: str
    registry: "ExecutorRegistry"


# --------------------------------------------------------------------------- #
# Binding result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionExecutorBindingResult:
    """Result of a binding policy evaluation."""
    enablement_id: str
    receiver_id: str
    policy_decision: str  # ALLOW or REJECT
    policy_reason: str
    binding_authorized: bool
    executor_identity: Optional[str] = None
    executor_factory: Optional[str] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Executor registry
# --------------------------------------------------------------------------- #

class ExecutorRegistry:
    """Maps receiver IDs to executor collaborators.

    No default executor. No automatic selection.
    """

    def __init__(self) -> None:
        self._executors: dict[str, ProductionExecutorProtocol] = {}

    def register(self, receiver_id: str, executor: ProductionExecutorProtocol) -> None:
        self._executors[receiver_id] = executor

    def resolve(self, receiver_id: str) -> Optional["ProductionExecutorProtocol"]:
        return self._executors.get(receiver_id)

    def has_executor(self, receiver_id: str) -> bool:
        return receiver_id in self._executors

    def unregister(self, receiver_id: str) -> bool:
        if receiver_id in self._executors:
            del self._executors[receiver_id]
            return True
        return False

    @property
    def bound_receivers(self) -> list[str]:
        return list(self._executors.keys())

    @property
    def bound_count(self) -> int:
        return len(self._executors)


# --------------------------------------------------------------------------- #
# Executor protocol
# --------------------------------------------------------------------------- #

class ProductionExecutorProtocol:
    """Protocol for executor collaborators."""

    @property
    def executor_id(self) -> str:
        raise NotImplementedError

    def execute(self, request: "ProductionExecutionRequest") -> "ProductionExecutorResult":
        raise NotImplementedError


@dataclass(frozen=True)
class ProductionExecutorResult:
    """Result from an executor."""
    executor_id: str
    execution_status: str
    output: Any = None
    reason: str = ""


@dataclass(frozen=True)
class ProductionExecutionRequest:
    """Explicit production execution request."""
    receiver_id: str
    delegation_id: str
    router_contract_id: str
    authority_contract_id: str
    transport_contract_id: str
    model_binding_id: str
    execution_scope: str
    task_payload: str
    attempt_limit: int = 1


# --------------------------------------------------------------------------- #
# Binding policy
# --------------------------------------------------------------------------- #

class ProductionExecutorBindingPolicy:
    """Permanent policy for production real-executor binding.

    Defaults to DENY. Only explicit eligibility passes.
    """

    def __init__(
        self,
        *,
        clock: BindingClock,
        max_simultaneous_bindings: int = MAX_SIMULTANEOUS_REAL_BINDINGS,
        max_ttl: int = MAX_BINDING_TTL_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_simultaneous_bindings = max_simultaneous_bindings
        self._max_ttl = max_ttl

    def evaluate(
        self,
        enablement: ProductionExecutorBindingEnablement,
        current_binding_count: int = 0,
        bound_enablements: dict[str, tuple[str, str]] | None = None,
    ) -> ProductionExecutorBindingResult:
        """Evaluate binding enablement against policy.

        Default decision is DENY. Only explicit eligibility passes.

        Args:
            enablement: The binding enablement to evaluate
            current_binding_count: Current number of active bindings
            bound_enablements: Optional dict of already-bound enablement IDs
                mapping to (receiver_id, canonical_hash)
        """
        if bound_enablements is None:
            bound_enablements = {}

        # Gate 1: Enablement must be enabled
        if not enablement.enabled:
            return self._reject(enablement, "ENABLEMENT_NOT_ENABLED")

        # Gate 2: Receiver must be present
        if not enablement.receiver_id:
            return self._reject(enablement, "MISSING_RECEIVER")

        # Gate 3: Receiver must be in qualified set
        if enablement.receiver_id not in QUALIFIED_RECEIVERS:
            return self._reject(enablement, "UNSUPPORTED_RECEIVER")

        # Gate 4: Runtime scope must be allowed
        if enablement.runtime_scope != ALLOWED_RUNTIME_SCOPE:
            return self._reject(enablement, "UNSUPPORTED_RUNTIME_SCOPE")

        # Gate 5: Delegation class must be allowed
        if enablement.delegation_class != ALLOWED_DELEGATION_CLASS:
            return self._reject(enablement, "DELEGATION_CLASS_MISMATCH")

        # Gate 6: Max bound executors must be positive
        if enablement.max_bound_executors < 1:
            return self._reject(enablement, "INVALID_BINDING_LIMIT")

        # Gate 8: Transport contract must match receiver binding
        receiver_bindings = QUALIFIED_RECEIVERS[enablement.receiver_id]
        if enablement.transport_contract_id != receiver_bindings["transport_contract_id"]:
            return self._reject(enablement, "TRANSPORT_CONTRACT_MISMATCH")

        # Gate 9: Model binding must match receiver binding
        if enablement.model_binding_id != receiver_bindings["model_binding_id"]:
            return self._reject(enablement, "MODEL_BINDING_MISMATCH")

        # Gate 10: Executor identity must match receiver binding
        qualified_executor = QUALIFIED_EXECUTOR_IMPLEMENTATIONS.get(enablement.receiver_id, {})
        if enablement.executor_identity != qualified_executor.get("executor_identity", ""):
            return self._reject(enablement, "EXECUTOR_IDENTITY_MISMATCH")

        if enablement.executor_factory != qualified_executor.get("executor_factory", ""):
            return self._reject(enablement, "EXECUTOR_FACTORY_MISMATCH")

        # Gate 11: Temporal integrity - parse timestamps and validate
        try:
            issued_dt = parse_iso_timestamp(enablement.issued_at)
        except ValueError:
            return self._reject(enablement, "MALFORMED_ISSUED_AT")

        try:
            expires_dt = parse_iso_timestamp(enablement.expires_at)
        except ValueError:
            return self._reject(enablement, "MALFORMED_EXPIRES_AT")

        # Temporal order: expires_at must be strictly after issued_at
        if expires_dt <= issued_dt:
            return self._reject(enablement, "INVALID_TEMPORAL_ORDER")

        # Compute effective lifetime as full-precision timedelta (NO int truncation)
        effective_lifetime = expires_dt - issued_dt

        # Parse requested TTL into exact Decimal
        try:
            requested_ttl = parse_requested_ttl(enablement.requested_ttl_seconds)
        except ValueError:
            return self._reject(enablement, "INVALID_REQUESTED_TTL")

        # Convert effective lifetime to Decimal seconds using integer microseconds
        # to avoid float representation artifacts
        effective_microseconds = (
            effective_lifetime.days * 86400000000
            + effective_lifetime.seconds * 1000000
            + effective_lifetime.microseconds
        )
        effective_seconds_decimal = Decimal(effective_microseconds) / Decimal("1000000")

        # Effective lifetime must not exceed policy maximum (full precision)
        policy_max_microseconds = self._max_ttl * 1000000
        if effective_microseconds > policy_max_microseconds:
            return self._reject(enablement, "EFFECTIVE_TTL_ABOVE_MAX")

        # Requested TTL must match effective lifetime exactly
        if requested_ttl != effective_seconds_decimal:
            return self._reject(enablement, "TTL_MISMATCH")

        # Gate 12: Actual expiration validation using injected clock
        now_str = self._clock.now_iso()
        try:
            now_dt = parse_iso_timestamp(now_str)
        except ValueError:
            return self._reject(enablement, "INVALID_CLOCK")

        if issued_dt > now_dt:
            return self._reject(enablement, "ENABLEMENT_NOT_YET_VALID")
        if expires_dt <= now_dt:
            return self._reject(enablement, "ENABLEMENT_EXPIRED")

        # Gate 13: Enablement-ID collision check (cross-receiver takes precedence)
        # This MUST come BEFORE binding limit to ensure correct semantic classification
        canonical_hash = sha256_payload(enablement.to_canonical_dict())
        if enablement.enablement_id in bound_enablements:
            existing_receiver, existing_hash = bound_enablements[enablement.enablement_id]
            if existing_receiver != enablement.receiver_id:
                return self._reject(enablement, "CROSS_RECEIVER_BINDING_REPLAY")
            if existing_hash != canonical_hash:
                return self._reject(enablement, "ENABLEMENT_ID_COLLISION")
            # Identical duplicate - idempotent, no new binding created
            return self._reject(enablement, "IDENTICAL_DUPLICATE")

        # Gate 14: Binding limit must not be exceeded (only for genuinely new bindings)
        if current_binding_count >= self._max_simultaneous_bindings:
            return self._reject(enablement, "BINDING_LIMIT_EXCEEDED")

        # All gates pass
        return self._allow(enablement)

    def _reject(
        self,
        enablement: ProductionExecutorBindingEnablement,
        reason: str,
    ) -> ProductionExecutorBindingResult:
        return ProductionExecutorBindingResult(
            enablement_id=enablement.enablement_id,
            receiver_id=enablement.receiver_id,
            policy_decision="REJECT",
            policy_reason=reason,
            binding_authorized=False,
        )

    def _allow(
        self,
        enablement: ProductionExecutorBindingEnablement,
    ) -> ProductionExecutorBindingResult:
        return ProductionExecutorBindingResult(
            enablement_id=enablement.enablement_id,
            receiver_id=enablement.receiver_id,
            policy_decision="ALLOW",
            policy_reason="POLICY_ALLOW",
            binding_authorized=True,
            executor_identity=enablement.executor_identity,
            executor_factory=enablement.executor_factory,
        )


# --------------------------------------------------------------------------- #
# Binding controller
# --------------------------------------------------------------------------- #

class ProductionExecutorBindingController:
    """Narrowest permanent controller for explicit binding and teardown.

    May NOT:
    - create a receiver selection
    - issue authority
    - issue activation
    - create execution requests
    - call GovernedProductionCoordinator.execute()
    - call ProductionExecutionBoundary.execute()
    - call the executor
    - call the adapter
    - start a process
    - invoke a model
    """

    def __init__(
        self,
        *,
        policy: ProductionExecutorBindingPolicy,
        clock: BindingClock,
    ) -> None:
        self._policy = policy
        self._clock = clock
        self._bound_enablements: dict[str, tuple[str, str, ProductionExecutorBindingHandle]] = {}

    def get_bound_handle(self, enablement_id: str) -> ProductionExecutorBindingHandle | None:
        """Retrieve existing bound handle for an enablement ID, if any."""
        entry = self._bound_enablements.get(enablement_id)
        if entry is None:
            return None
        return entry[2]

    def get_binding_for_receiver(self, receiver_id: str) -> ProductionExecutorBindingHandle | None:
        """Retrieve existing bound handle for a receiver ID, if any."""
        for entry in self._bound_enablements.values():
            if entry[0] == receiver_id:
                return entry[2]
        return None

    @property
    def active_binding_count(self) -> int:
        """Return the number of active bindings."""
        return len(self._bound_enablements)

    def bind(
        self,
        enablement: ProductionExecutorBindingEnablement,
        registry: ExecutorRegistry,
        executor_factory: Any = None,
    ) -> ProductionExecutorBindingHandle:
        """Bind a qualified real executor into the registry after policy approval.

        The binding handle inherits the exact validated expiration from the enablement.
        No TTL recomputation occurs at bind time.

        Returns a binding handle on success.
        Raises BindingPolicyError on rejection.
        """
        # Evaluate policy with current binding count and bound enablements
        # POLICY CLASSIFICATION MUST PRECEDE any existing-handle resolution
        # Pass only receiver_id and canonical_hash (not handle) to policy
        bound_meta = {k: (v[0], v[1]) for k, v in self._bound_enablements.items()}
        result = self._policy.evaluate(enablement, self.active_binding_count, bound_meta)

        # Only IDENTICAL_DUPLICATE may resolve to an existing handle
        # All other results (ALLOW, COLLISION, REPLAY, other REJECT) are handled here
        if not result.binding_authorized:
            # Check if this is an identical duplicate - return existing handle
            if result.policy_reason == "IDENTICAL_DUPLICATE":
                existing_handle = self.get_bound_handle(enablement.enablement_id)
                if existing_handle is not None:
                    # Return existing handle without refreshing expiry
                    return existing_handle

            # All other rejections raise BindingPolicyError
            raise BindingPolicyError(result.policy_reason, result.policy_decision)

        # Pre-registration expiry check (fail-closed for race condition)
        # The enablement may have expired between policy evaluation and registry mutation
        now_str = self._clock.now_iso()
        try:
            now_dt = parse_iso_timestamp(now_str)
            expires_dt = parse_iso_timestamp(enablement.expires_at)
        except ValueError:
            raise BindingPolicyError("INVALID_CLOCK_OR_EXPIRY", "REJECT")

        if expires_dt <= now_dt:
            raise BindingPolicyError("ENABLEMENT_EXPIRED", "REJECT")

        # Resolve executor implementation
        if executor_factory is None:
            executor_factory = self._resolve_executor_factory(result.executor_factory)

        # Create executor instance
        executor = executor_factory()

        # Register into registry
        registry.register(enablement.receiver_id, executor)

        # Handle inherits exact validated expires_at from enablement
        # NO recomputation from bind time + TTL
        bound_at = now_str
        handle_expires_at = enablement.expires_at

        # Create handle
        handle = ProductionExecutorBindingHandle(
            binding_id=f"binding-{uuid.uuid4()}",
            enablement_id=enablement.enablement_id,
            receiver_id=enablement.receiver_id,
            executor_identity=result.executor_identity or "unknown",
            bound_at=bound_at,
            expires_at=handle_expires_at,
            registry=registry,
        )

        # Record the bound enablement for duplicate detection
        canonical_hash = sha256_payload(enablement.to_canonical_dict())
        self._bound_enablements[enablement.enablement_id] = (
            enablement.receiver_id,
            canonical_hash,
            handle,
        )

        return handle

    def remove_expired_binding(
        self,
        receiver_id: str,
        *,
        expected_enablement_id: str | None = None,
        expected_binding_id: str | None = None,
    ) -> bool:
        """Remove an expired binding entry from the active ledger and registry.

        Narrow lifecycle API for synchronous expiration cleanup.
        Only removes the binding for the specified receiver_id.

        Validates authoritative binding identity before mutation:
        - If expected_enablement_id is provided, must match the authoritative enablement ID
        - If expected_binding_id is provided, must match the authoritative binding ID

        Returns True if an entry was removed, False if no matching entry existed.
        Raises BindingPolicyError if identity validation fails.
        """
        # Find the enablement_id for this receiver
        target_eid = None
        for eid, entry in self._bound_enablements.items():
            if entry[0] == receiver_id:
                target_eid = eid
                break

        if target_eid is None:
            return False

        # Validate authoritative binding identity
        handle = self._bound_enablements[target_eid][2]
        if expected_enablement_id is not None and handle.enablement_id != expected_enablement_id:
            raise BindingPolicyError("ENABLEMENT_ID_MISMATCH", "REJECT")
        if expected_binding_id is not None and handle.binding_id != expected_binding_id:
            raise BindingPolicyError("BINDING_ID_MISMATCH", "REJECT")

        # Remove from registry first (authoritative lifecycle owner)
        handle.registry.unregister(receiver_id)

        # Remove from active ledger
        del self._bound_enablements[target_eid]
        return True

    def teardown(self, binding: ProductionExecutorBindingHandle) -> bool:
        """Teardown/unregister the exact binding.

        Returns True if binding was removed, False if not found.
        """
        removed = binding.registry.unregister(binding.receiver_id)
        if removed:
            # Clean up bound enablements entry
            self._bound_enablements.pop(binding.enablement_id, None)
        return removed

    def _resolve_executor_factory(self, factory_path: str | None) -> Any:
        """Resolve executor factory from qualified path."""
        if not factory_path:
            raise BindingPolicyError("MISSING_EXECUTOR_FACTORY", "REJECT")

        # Parse module:class format
        parts = factory_path.split(":")
        if len(parts) != 2:
            raise BindingPolicyError("INVALID_EXECUTOR_FACTORY", "REJECT")

        module_path, class_name = parts

        # Import module and get class
        import importlib
        module = importlib.import_module(module_path)
        factory = getattr(module, class_name)

        return factory


class BindingPolicyError(Exception):
    """Raised when binding policy rejects a request."""

    def __init__(self, reason: str, decision: str = "REJECT") -> None:
        super().__init__(f"Binding policy {decision}: {reason}")
        self.reason = reason
        self.decision = decision


# --------------------------------------------------------------------------- #
# Binding contract computation
# --------------------------------------------------------------------------- #

def compute_ea4e21_binding_contract_id() -> str:
    """Compute the deterministic EA-4E.21 binding contract ID."""
    canonical = {
        "schema_id": BINDING_SCHEMA_ID,
        "schema_version": BINDING_SCHEMA_VERSION,
        "qualified_receivers": {
            k: {
                "transport_contract_id": QUALIFIED_RECEIVERS[k]["transport_contract_id"],
                "model_binding_id": QUALIFIED_RECEIVERS[k]["model_binding_id"],
                "executor_identity": QUALIFIED_EXECUTOR_IMPLEMENTATIONS[k]["executor_identity"],
            }
            for k in sorted(QUALIFIED_RECEIVERS.keys())
        },
        "ea4e17_issuance_contract_id": compute_ea4e17_issuance_contract_id(),
        "ea4e18_integration_contract_id": compute_ea4e18_integration_contract_id(),
        "allowed_runtime_scope": ALLOWED_RUNTIME_SCOPE,
        "allowed_delegation_class": ALLOWED_DELEGATION_CLASS,
        "max_binding_ttl": MAX_BINDING_TTL_SECONDS,
        "max_simultaneous_bindings": MAX_SIMULTANEOUS_REAL_BINDINGS,
        "default_binding_decision": DEFAULT_BINDING_DECISION,
        "runtime_only": True,
        "ttl_required": True,
        "unbounded_binding_allowed": False,
        "expired_enablement_rejected": True,
        "ttl_above_max_rejected": True,
        "binding_limit_enforced": True,
        "cross_receiver_binding_replay_distinct": True,
        "cross_receiver_binding_replay_precedence": True,
        "no_automatic_receiver_selection": True,
        "no_retry": True,
        "no_fallback": True,
        "no_failover": True,
        "teardown_required": True,
        "temporal_precision": {
            "full_precision_temporal_comparison": True,
            "effective_lifetime_int_truncation": False,
            "effective_lifetime_rounding": False,
            "subsecond_precision_preserved": True,
            "policy_max_ttl_seconds": MAX_BINDING_TTL_SECONDS,
            "artifact_requested_ttl_field": "requested_ttl_seconds",
            "requested_ttl_consistency": "exact_equality_microseconds",
            "requested_ttl_canonicalization": "normalized_decimal_string",
            "requested_ttl_subsecond_support": True,
            "binary_float_exact_equality": False,
            "comparison_method": "integer_microseconds",
        },
        "temporal_integrity": {
            "timezone_required": True,
            "timestamps_parsed_chronologically": True,
            "raw_lexical_timestamp_comparison": False,
            "expires_at_must_be_after_issued_at": True,
            "effective_lifetime_derived_from_timestamps": True,
            "max_effective_lifetime_seconds": MAX_BINDING_TTL_SECONDS,
            "exact_expiration_boundary": "expired",
            "future_issued_behavior": "reject",
            "declared_ttl_consistency": "exact_equality",
            "malformed_timestamp_behavior": "reject",
        },
        "runtime_handle_expiry": {
            "binding_handle_expiry_source": "validated_enablement_expires_at",
            "binding_handle_expiry_recomputed_from_bind_time": False,
            "binding_handle_expiry_ttl_truncation": False,
            "binding_handle_expiry_reset": False,
            "binding_handle_expiry_extension": False,
            "duplicate_binding_expiry_refresh": False,
            "pre_registration_expiry_check": True,
        },
        "controller_replay_enforcement": {
            "same_id_fast_path_before_policy": False,
            "policy_classification_precedes_existing_handle_return": True,
            "existing_handle_return_requires_identical_duplicate": True,
            "collision_returns_handle": False,
            "cross_receiver_replay_returns_handle": False,
            "executor_resolution_after_replay_classification": True,
            "duplicate_registration": False,
            "duplicate_expiry_refresh": False,
            "bound_enablement_state_semantics": "ACTIVE_BINDINGS_ONLY",
        },
    }
    return sha256_payload(canonical)
