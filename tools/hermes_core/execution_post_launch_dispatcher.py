"""EA-4D.4E gated production-ready dispatch boundary (mechanics slice).

This is the thin production-dispatch boundary between a future real production
caller (EA-4D.4F) and the already-proven post-launch orchestration chain:

    4E (this module)
        -> 4D PostLaunchExecutionOrchestrator.run_post_launch(...)
        -> 4A ExecutionStartResultService.reconcile_start_result(...)
        -> 4C ExecutionStateProjectionOrchestrator (policy gate)
        -> 4B ExecutionStateProjector (authoritative EXECUTING projection)

4E owns ONLY the dispatch-policy boundary. It does NOT own post-launch
authority semantics. It never reaches 4A/4B/4C directly, never launches or
looks up runtime, never creates or mutates authority artifacts, and performs
ZERO automatic retries.

Design scope (EA-4D.4E frozen design):

    ExecutionPostLaunchDispatcher(
        *, post_launch_orchestrator, enabled: bool = False
    ).dispatch_post_launch(launch_attempt_id: str) -> PostLaunchExecutionResult

    enabled == False
        -> ExecutionPostLaunchDispatchDisabledError
        -> 4D NOT invoked (no 4A/4B/4C reached; no projection; no event)

    enabled == True
        -> exactly one post_launch_orchestrator.run_post_launch(launch_attempt_id)
        -> return PostLaunchExecutionResult unchanged
        -> propagate typed errors unchanged

    automatic retries = ZERO

No external configuration reader exists in 4E. The gate is constructor-owned;
a future composition slice (EA-4D.4F) may map environment/application
configuration into the ``enabled`` flag. There is no hot reload and no second
gate authority.
"""

from __future__ import annotations

from tools.hermes_core.post_launch_execution_orchestrator import (
    PostLaunchExecutionOrchestrator,
    PostLaunchExecutionResult,
)


# Constructor-owned gate default. No external config reader, no hot reload.
EXECUTION_POST_LAUNCH_DISPATCH_ENABLED_DEFAULT = False


class ExecutionPostLaunchDispatchDisabledError(Exception):
    """4E-local, typed, non-durable policy error.

    Raised when the dispatcher is invoked while its gate is disabled. It is NOT
    hashed and NOT persisted. It means only that production dispatch is
    currently off; it must not be interpreted as a worker, runtime, or
    authority-state failure.
    """


class ExecutionPostLaunchDispatcher:
    """Gated production-ready boundary that invokes the 4D orchestrator.

    This module is the production-dispatch boundary only. In EA-4D.4E it has NO
    upstream production caller and performs NO automatic wiring (those are
    EA-4D.4F scope). It can be explicitly invoked in tests / manual trusted
    contexts.
    """

    def __init__(
        self,
        *,
        post_launch_orchestrator: PostLaunchExecutionOrchestrator,
        enabled: bool = EXECUTION_POST_LAUNCH_DISPATCH_ENABLED_DEFAULT,
    ) -> None:
        self._post_launch_orchestrator = post_launch_orchestrator
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def dispatch_post_launch(
        self,
        launch_attempt_id: str,
    ) -> PostLaunchExecutionResult:
        """Dispatch post-launch orchestration for one launch attempt.

        Args:
            launch_attempt_id: str supplied by an explicit trusted/manual/test
                invoker in this slice. The dispatcher consumes it; it does not
                create, derive, mutate, or claim lifecycle ownership of it.

        Returns:
            PostLaunchExecutionResult, passed through unchanged from 4D.

        Raises:
            ExecutionPostLaunchDispatchDisabledError: when the gate is off; 4D
                is NOT invoked.
            PostLaunchExecutionError / ExecutionStartResultError /
            ExecutionStateProjectionConflictError /
            ExecutionStateProjectionIntegrityError /
            ExecutionStateProjectionIneligibleError: propagated unchanged from
            the lower layers (4A/4C/4B via 4D).
        """
        if not self._enabled:
            raise ExecutionPostLaunchDispatchDisabledError(
                "production post-launch dispatch is disabled; "
                "4D was not invoked"
            )

        # Exactly one downstream call. No retry, sleep, poll, or background work.
        return self._post_launch_orchestrator.run_post_launch(launch_attempt_id)
