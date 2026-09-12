"""EA-4E.9 live Kilo dispatch layer — single-shot qualification only.

This module provides a live dispatch layer that invokes the real Kilo
adapter exactly once when all authority gates pass.

SCOPE: Single live Kilo invocation for EA-4E.9 qualification only.
"""

from __future__ import annotations

import uuid
from typing import Optional

from tools.hermes_core.kilo_adapter import KiloAdapter
from tools.hermes_core.receiver_router import (
    RoutingRequest,
    get_default_router,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    DispatchDecision,
    ExecutionAuthorityValidator,
)


class LiveKiloDispatchLayer:
    """Live dispatch layer for single-shot Kilo qualification.

    Invokes the real Kilo adapter exactly once when:
    - Route decision is SELECTED
    - Authority is valid
    - Dispatch decision is AUTHORIZED

    Tracks invocation count to enforce single-shot semantics.
    """

    def __init__(self, *, kilo_executable: str | None = None) -> None:
        self._router = get_default_router()
        self._validator = ExecutionAuthorityValidator(
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
        authority: DispatchAuthority | None,
        delegation_class: str = "governed",
        task_message: str = "Return exactly: EA4E9_KILO_LIVE_OK",
    ) -> "LiveKiloResult":
        """Dispatch through the production path with live Kilo execution.

        Enforces single-shot semantics: at most one live invocation.
        """
        # Step 1: Route selection
        route_result = self._router.route(RoutingRequest(
            receiver_id=receiver_id,
            execution_authority_present=authority is not None,
        ))

        if route_result.route_decision != "SELECTED":
            return LiveKiloResult(
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason=route_result.route_reason,
                process_started=False,
            )

        # Step 2: Authority validation
        dispatch_result = self._validator.validate(authority, route_result)

        if dispatch_result.dispatch_decision != "AUTHORIZED":
            return LiveKiloResult(
                route_decision=dispatch_result.route_decision,
                authority_valid=dispatch_result.authority_valid,
                dispatch_decision=dispatch_result.dispatch_decision,
                reason=dispatch_result.reason,
                process_started=False,
            )

        # Step 3: Single-shot enforcement
        if self._invocation_count >= self._max_invocations:
            return LiveKiloResult(
                route_decision="SELECTED",
                authority_valid=True,
                dispatch_decision="REJECT",
                reason="LIVE_INVOCATION_BUDGET_EXHAUSTED",
                process_started=False,
            )

        # Step 4: Live Kilo invocation
        self._invocation_count += 1
        config = {"task_message": task_message}
        if self._kilo_executable:
            config["kilo_executable"] = self._kilo_executable
        adapter = KiloAdapter(config=config)

        outcome = adapter.execute(
            idempotency_key=f"ea4e9-{uuid.uuid4()}",
            launch_attempt_id=f"ea4e9-launch-{uuid.uuid4()}",
            delegation_id=f"ea4e9-delegation-{uuid.uuid4()}",
            stdin_data="",
        )

        return LiveKiloResult(
            route_decision="SELECTED",
            authority_valid=True,
            dispatch_decision="AUTHORIZED",
            reason="LIVE_KILO_DISPATCHED",
            process_started=outcome.process_started,
            pid=outcome.record.pid,
            terminal_state=outcome.record.terminal_state,
            verified_result=outcome.verified_result,
        )


class LiveKiloResult:
    """Result of a live Kilo dispatch attempt."""

    def __init__(
        self,
        *,
        route_decision: str,
        authority_valid: bool,
        dispatch_decision: str,
        reason: str,
        process_started: bool,
        pid: int | None = None,
        terminal_state: str | None = None,
        verified_result=None,
    ) -> None:
        self.route_decision = route_decision
        self.authority_valid = authority_valid
        self.dispatch_decision = dispatch_decision
        self.reason = reason
        self.process_started = process_started
        self.pid = pid
        self.terminal_state = terminal_state
        self.verified_result = verified_result
