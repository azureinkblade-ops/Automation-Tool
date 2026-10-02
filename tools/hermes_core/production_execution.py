"""EA-4E.14 reusable production execution boundary.

This module establishes the permanent production execution abstraction
sitting downstream of routing, authority, activation, and resolution.

Logical flow:

    ProductionDispatchRequest
    → ReceiverRouter
    → ExecutionAuthorityValidator
    → ProductionActivationValidator
    → ReceiverAdapterResolver
    → ProductionExecutionBoundary
    → injected fake/inert receiver executor
    → ProductionExecutionResult
    → NO PROCESS START

Core invariant:
    ROUTING != AUTHORIZATION != ACTIVATION != RESOLUTION != EXECUTION

The execution boundary NEVER:
    - selects a receiver
    - creates authority
    - creates activation
    - retries
    - falls back
    - infers receiver from task text or environment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
    get_default_router,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    ExecutionAuthorityValidator,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import (
    ProductionActivation,
    ProductionActivationValidator,
    compute_ea4e11_activation_contract_id,
)


# --------------------------------------------------------------------------- #
# Execution schema
# --------------------------------------------------------------------------- #

EXECUTION_SCHEMA_ID = "hermes.production-execution.receiver-dispatch/v1"
EXECUTION_SCHEMA_VERSION = "ea4e.14"
EXECUTION_ARTIFACT_VERSION = "1"


# --------------------------------------------------------------------------- #
# Executor protocol
# --------------------------------------------------------------------------- #

class ProductionExecutorProtocol:
    """Protocol for executor collaborators.

    Executors MUST be inert by default — they receive a request and
    return a result without starting processes.
    """

    @property
    def executor_id(self) -> str:
        raise NotImplementedError

    def execute(self, request: "ProductionExecutionRequest") -> "ProductionExecutorResult":
        raise NotImplementedError


@dataclass(frozen=True)
class ProductionExecutorResult:
    """Result from an executor."""
    executor_id: str
    execution_status: str  # "SUCCESS" or "FAILED"
    output: Any = None
    reason: str = ""


# --------------------------------------------------------------------------- #
# Fake executors for qualification
# --------------------------------------------------------------------------- #

class FakeKiloExecutor:
    """Inert Kilo executor for qualification. Never starts a process."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "fake-kilo-executor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request: "ProductionExecutionRequest") -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E14_KILO_FAKE_EXECUTION_OK",
            reason="FAKE_EXECUTION",
        )


class FakeOpenCodeExecutor:
    """Inert OpenCode executor for qualification. Never starts a process."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "fake-opencode-executor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request: "ProductionExecutionRequest") -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E14_OPENCODE_FAKE_EXECUTION_OK",
            reason="FAKE_EXECUTION",
        )


# --------------------------------------------------------------------------- #
# Execution request
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionExecutionRequest:
    """Explicit production execution request.

    Contains only what has already been validated by upstream gates.
    """
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
# Production execution result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionExecutionResult:
    """Structured result from production execution boundary."""
    receiver_id: Optional[str]
    route_decision: str
    authority_valid: bool
    activation_valid: bool
    adapter_resolution: Optional[str]
    execution_decision: str
    executor_called: bool
    executor_id: Optional[str]
    execution_status: Optional[str]
    real_adapter_called: bool = False
    process_started: bool = False
    model_invoked: bool = False
    reason: str = ""
    attempt_count: int = 0
    executor_output: Any = None


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

    def resolve(self, receiver_id: str) -> Optional[ProductionExecutorProtocol]:
        return self._executors.get(receiver_id)

    def has_executor(self, receiver_id: str) -> bool:
        return receiver_id in self._executors


# --------------------------------------------------------------------------- #
# Production execution boundary
# --------------------------------------------------------------------------- #

class ProductionExecutionBoundary:
    """Reusable production execution boundary.

    Receives already-validated decisions and delegates to executor collaborators.
    NEVER creates authority, activation, or selects receivers.
    """

    def __init__(
        self,
        *,
        router: Optional[Any] = None,
        authority_validator: Optional[ExecutionAuthorityValidator] = None,
        activation_validator: Optional[ProductionActivationValidator] = None,
        executor_registry: Optional[ExecutorRegistry] = None,
    ) -> None:
        self._router = router or get_default_router()
        self._authority_validator = authority_validator or ExecutionAuthorityValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._activation_validator = activation_validator or ProductionActivationValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._executor_registry = executor_registry or ExecutorRegistry()

    def execute(
        self,
        *,
        receiver_id: str,
        authority: Optional[DispatchAuthority],
        activation: Optional[ProductionActivation],
        execution_request: ProductionExecutionRequest,
    ) -> ProductionExecutionResult:
        """Execute the full production path through to executor.

        NEVER starts a process. Uses injected executor collaborators only.
        """
        # Step 1: Route selection (EA-4E.6)
        route_result = self._router.route(RoutingRequest(
            receiver_id=receiver_id,
            execution_authority_present=authority is not None,
        ))

        if route_result.route_decision != "SELECTED":
            return ProductionExecutionResult(
                receiver_id=None,
                route_decision=route_result.route_decision,
                authority_valid=False,
                activation_valid=False,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                executor_id=None,
                execution_status=None,
                reason=route_result.route_reason,
            )

        # Step 2: Authority validation (EA-4E.7)
        authority_result = self._authority_validator.validate(authority, route_result)
        if authority_result.dispatch_decision != "AUTHORIZED":
            return ProductionExecutionResult(
                receiver_id=receiver_id,
                route_decision=authority_result.route_decision,
                authority_valid=authority_result.authority_valid,
                activation_valid=False,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                executor_id=None,
                execution_status=None,
                reason=authority_result.reason,
            )

        # Step 3: Activation validation (EA-4E.11)
        activation_result = self._activation_validator.validate(
            activation, receiver_id=receiver_id
        )
        if activation_result.dispatch_decision != "AUTHORIZED":
            return ProductionExecutionResult(
                receiver_id=receiver_id,
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=False,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                executor_id=None,
                execution_status=None,
                reason=activation_result.reason,
            )

        # Step 4: Adapter resolution
        if receiver_id not in QUALIFIED_RECEIVERS:
            return ProductionExecutionResult(
                receiver_id=receiver_id,
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                executor_id=None,
                execution_status=None,
                reason="UNSUPPORTED_RECEIVER",
            )

        adapter_kind = QUALIFIED_RECEIVERS[receiver_id].get("receiver_class", "UNKNOWN")

        # Step 5: Executor resolution
        executor = self._executor_registry.resolve(receiver_id)
        if executor is None:
            return ProductionExecutionResult(
                receiver_id=receiver_id,
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                adapter_resolution=adapter_kind,
                execution_decision="REJECT",
                executor_called=False,
                executor_id=None,
                execution_status=None,
                reason="EXECUTOR_NOT_CONFIGURED",
            )

        # Step 6: Execution budget check
        if execution_request.attempt_limit < 1:
            return ProductionExecutionResult(
                receiver_id=receiver_id,
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                adapter_resolution=adapter_kind,
                execution_decision="REJECT",
                executor_called=False,
                executor_id=None,
                execution_status=None,
                reason="EXECUTION_BUDGET_EXHAUSTED",
            )

        # Step 7: Execute via injected collaborator (NEVER live)
        executor_result = executor.execute(execution_request)

        return ProductionExecutionResult(
            receiver_id=receiver_id,
            route_decision="SELECTED",
            authority_valid=True,
            activation_valid=True,
            adapter_resolution=adapter_kind,
            execution_decision="EXECUTE",
            executor_called=True,
            executor_id=executor.executor_id,
            execution_status=executor_result.execution_status,
            real_adapter_called=False,
            process_started=False,
            model_invoked=False,
            reason=executor_result.reason,
            attempt_count=1,
            executor_output=executor_result.output,
        )


# --------------------------------------------------------------------------- #
# Canonical material
# --------------------------------------------------------------------------- #

def get_execution_canonical_material() -> dict[str, Any]:
    """Return deterministic canonical material for EA-4E.14 execution contract."""
    return {
        "schema_id": EXECUTION_SCHEMA_ID,
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "artifact_version": EXECUTION_ARTIFACT_VERSION,
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "authority_contract_id": compute_ea4e7_authority_contract_id(),
        "activation_contract_id": compute_ea4e11_activation_contract_id(),
        "qualified_receivers": {
            k: QUALIFIED_RECEIVERS[k] for k in sorted(QUALIFIED_RECEIVERS)
        },
        "execution_default": "DISABLED",
        "real_executors_configured_by_default": False,
        "fail_closed_behaviors": [
            "UNSUPPORTED_RECEIVER",
            "EXECUTOR_NOT_CONFIGURED",
            "EXECUTION_BUDGET_EXHAUSTED",
        ],
        "security_invariants": {
            "router_creates_execution_authority": False,
            "authority_validator_creates_activation": False,
            "activation_validator_creates_execution_authority": False,
            "execution_boundary_creates_execution_authority": False,
            "execution_boundary_creates_activation": False,
            "execution_boundary_selects_receiver": False,
            "execution_boundary_starts_receiver_by_default": False,
        },
    }


def compute_ea4e14_execution_contract_id() -> str:
    """Compute the canonical EA-4E.14 execution contract ID."""
    return sha256_payload(get_execution_canonical_material())
