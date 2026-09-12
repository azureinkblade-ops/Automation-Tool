"""EA-4E.12 Kilo production activation single-shot qualification harness.

This module provides a qualification-only harness that injects a real Kilo
adapter at the final seam of the EA-4E.11 production activation path.

SCOPE: Single live Kilo production activation for EA-4E.12 qualification only.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Optional

from tools.hermes_core.kilo_adapter import KiloAdapter
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
    get_default_router,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    DispatchAuthorityScope,
    ExecutionAuthorityValidator,
    build_dispatch_authority,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import (
    ProductionActivation,
    ProductionActivationValidator,
    build_production_activation,
    compute_ea4e11_activation_contract_id,
)


class ProductionKiloQualificationHarness:
    """Qualification-only harness for single-shot Kilo production activation.

    Preserves all EA-4E.6/7/11 gates while injecting a real Kilo adapter
    at the final seam.

    Enforces single-shot semantics: at most one live invocation.
    """

    def __init__(self, *, kilo_executable: str | None = None) -> None:
        self._router = get_default_router()
        self._authority_validator = ExecutionAuthorityValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._activation_validator = ProductionActivationValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._kilo_executable = kilo_executable
        self._invocation_count = 0
        self._max_invocations = 1

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def dispatch(
        self,
        *,
        receiver_id: str,
        authority: Optional[DispatchAuthority],
        activation: Optional[ProductionActivation],
        task_message: str = "Return exactly: EA4E12_KILO_PRODUCTION_OK",
    ) -> "KiloProductionResult":
        """Execute the full production activation path with real Kilo.

        Enforces single-shot semantics: at most one live invocation.
        """
        # Step 1: Route selection (EA-4E.6)
        route_result = self._router.route(RoutingRequest(
            receiver_id=receiver_id,
            execution_authority_present=authority is not None,
        ))

        if route_result.route_decision != "SELECTED":
            return KiloProductionResult(
                route_decision=route_result.route_decision,
                authority_valid=False,
                activation_valid=False,
                dispatch_decision="REJECT",
                adapter_resolution=None,
                reason=route_result.route_reason,
                process_started=False,
            )

        # Step 2: Authority validation (EA-4E.7)
        authority_result = self._authority_validator.validate(authority, route_result)
        if authority_result.dispatch_decision != "AUTHORIZED":
            return KiloProductionResult(
                route_decision=authority_result.route_decision,
                authority_valid=authority_result.authority_valid,
                activation_valid=False,
                dispatch_decision="REJECT",
                adapter_resolution=None,
                reason=authority_result.reason,
                process_started=False,
            )

        # Step 3: Activation validation (EA-4E.11)
        activation_result = self._activation_validator.validate(
            activation, receiver_id=receiver_id
        )
        if activation_result.dispatch_decision != "AUTHORIZED":
            return KiloProductionResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=False,
                dispatch_decision="REJECT",
                adapter_resolution=None,
                reason=activation_result.reason,
                process_started=False,
            )

        # Step 4: Single-shot enforcement
        if self._invocation_count >= self._max_invocations:
            return KiloProductionResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                dispatch_decision="REJECT",
                adapter_resolution="KILO",
                reason="LIVE_INVOCATION_BUDGET_EXHAUSTED",
                process_started=False,
            )

        # Step 5: Real Kilo adapter injection
        self._invocation_count += 1
        config = {"task_message": task_message}
        if self._kilo_executable:
            config["kilo_executable"] = self._kilo_executable
        adapter = KiloAdapter(config=config)

        outcome = adapter.execute(
            idempotency_key=f"ea4e12-{uuid.uuid4()}",
            launch_attempt_id=f"ea4e12-launch-{uuid.uuid4()}",
            delegation_id=f"ea4e12-delegation-{uuid.uuid4()}",
            stdin_data="",
        )

        return KiloProductionResult(
            route_decision="SELECTED",
            authority_valid=True,
            activation_valid=True,
            dispatch_decision="AUTHORIZED",
            adapter_resolution="KILO",
            reason="KILO_PRODUCTION_ACTIVATED",
            process_started=outcome.process_started,
            pid=outcome.record.pid,
            terminal_state=outcome.record.terminal_state,
            verified_result=outcome.verified_result,
        )


class KiloProductionResult:
    """Result of a Kilo production activation attempt."""

    def __init__(
        self,
        *,
        route_decision: str,
        authority_valid: bool,
        activation_valid: bool,
        dispatch_decision: str,
        adapter_resolution: Optional[str],
        reason: str,
        process_started: bool,
        pid: int | None = None,
        terminal_state: str | None = None,
        verified_result=None,
    ) -> None:
        self.route_decision = route_decision
        self.authority_valid = authority_valid
        self.activation_valid = activation_valid
        self.dispatch_decision = dispatch_decision
        self.adapter_resolution = adapter_resolution
        self.reason = reason
        self.process_started = process_started
        self.pid = pid
        self.terminal_state = terminal_state
        self.verified_result = verified_result
