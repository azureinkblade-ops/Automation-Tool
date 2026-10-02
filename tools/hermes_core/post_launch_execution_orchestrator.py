"""EA-4D.4D trusted post-launch authority orchestration (mechanics slice).

This is the thin orchestration owner that sequences the durable post-launch
transition the production chain was missing:

    explicit trusted/manual/test invocation
        -> PostLaunchExecutionOrchestrator.run_post_launch(...)
        -> 4A ExecutionStartResultService.reconcile_start_result(...)
        -> if persisted STARTED and 4C enabled:
               ExecutionStateProjectionOrchestrator.project_executing_for_started(...)
        -> 4B commits the immutable EXECUTING projection

It is ORCHESTRATION ONLY. It owns no activation boolean and no policy gate: the
4C orchestrator (already constructed, enabled or not) is injected. 4D inspects
the returned 4A ``ExecutionStartResult.outcome`` for control flow only; it does
NOT re-verify STARTED eligibility (4B does, authoritatively).

Frozen behavior (EA-4D.4D design, including the final micro-freeze):

    run_post_launch(launch_attempt_id) -> PostLaunchExecutionResult

    PostLaunchExecutionResult is IN-MEMORY ONLY. It is never hashed or
    persisted. Statuses (EXACTLY three; no fourth UNRESOLVED status):
        STARTED_PROJECTED        (4C enabled, 4B projected EXECUTING)
        STARTED_NOT_PROJECTED    (4C disabled -> DisabledError handled)
        FAILED_RECORDED          (4A FAILED; 4C not called)

    These three are DISTINCT from a non-definitive reconciliation:
        FAILED_RECORDED != STARTED_NOT_PROJECTED != non-definitive

    Exact flow:
        1. result = reconcile_start_result(launch_attempt_id)
           (4A raises a typed ExecutionStartResultError -> propagate unchanged;
            no 4C)
        2. result is None (NOT_FOUND_AUTHORITATIVE / UNKNOWN) ->
           raise PostLaunchExecutionError; no 4C invocation.
           PostLaunchExecutionError is 4D-local, typed, non-runtime,
           non-durable, not hashed, not persisted. It means only: post-launch
           reconciliation did not produce a definitive persisted STARTED or
           FAILED result. It guarantees: 4C not invoked, no projection, no
           ATTEMPT_EXECUTING event, no route mutation, no StartResult mutation,
           no ExecutionAttempt mutation, no relaunch.
        3. result.outcome == FAILED  -> FAILED_RECORDED (4C not called)
        4. result.outcome == STARTED:
               try: projection = 4C.project_executing_for_started(...)
               except ExecutionStateProjectionDisabledError:
                   return STARTED_NOT_PROJECTED
               except (4B conflict/integrity/ineligible): propagate unchanged
               else: return STARTED_PROJECTED

    Retry semantics: a PostLaunchExecutionError (result None) is retryable only
    by explicitly invoking run_post_launch(same launch_attempt_id) again. The
    retry may call 4A reconciliation again. It must not cause worker relaunch,
    a new LaunchAttempt, a route change, a background retry, or a scheduler
    retry. A later definitive result then proceeds normally.

    Runtime-lookup scope: 4D adds NO runtime-lookup capability and does NOT
    invoke RuntimeStartLookup directly. The accurate invariant is that 4D has
    no RuntimeStartLookup dependency of its own; 4A's reconcile_start_result()
    may internally use its already-authorized RuntimeStartLookup. That is reuse
    of closed 4A behavior, not a new 4D runtime capability.

This module does NOT:
* launch or look up runtime (no RuntimeLaunchAdapter / RuntimeStartLookup use);
* mutate routes, LaunchAttempts, StartResults, or ExecutionAttempts;
* create any new durable authority artifact (observability only);
* call 4B (execution_state_projector) directly.

Four-way boundary (frozen):

    LAUNCH_ATTEMPT_RECORDED
    != WORKER STARTED
    != ExecutionStartResult persisted
    != ExecutionStateProjection(EXECUTING) committed

4A owns the durable StartResult. 4C owns the projection policy. 4B owns
authoritative STARTED verification + the EXECUTING projection. 4D owns
orchestration only.

No production, scheduler, or default-coordinator caller is wired in this slice.
Invocation is restricted to explicit trusted/manual/test orchestration. A later
governance slice (EA-4D.4E) may authorize an actual production caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .execution_start import ExecutionStartOutcome
from .execution_start_result_service import ExecutionStartResultService
from .execution_state_projection_orchestrator import (
    ExecutionStateProjectionDisabledError,
    ExecutionStateProjectionOrchestrator,
)


class PostLaunchStatus(str, Enum):
    """Definitive post-launch resolution status (in-memory only)."""

    STARTED_PROJECTED = "STARTED_PROJECTED"
    STARTED_NOT_PROJECTED = "STARTED_NOT_PROJECTED"
    FAILED_RECORDED = "FAILED_RECORDED"


class PostLaunchExecutionError(Exception):
    """Raised when reconciliation is non-definitive / unresolved.

    This is NOT a status: there is no durable post-launch resolution to report.
    The frozen design propagates the unresolved condition rather than mapping it
    onto one of the three definitive statuses.
    """


@dataclass(frozen=True)
class PostLaunchExecutionResult:
    """In-memory orchestration result. Never hashed or persisted."""

    launch_attempt_id: str
    status: PostLaunchStatus
    start_result: Optional[object] = None
    projection: Optional[object] = None


class PostLaunchExecutionOrchestrator:
    """Sequences reconcile -> (optionally) 4C projection for one launch attempt.

    Construction is explicit and trusted: the caller supplies an already-built
    4A result service and an already-constructed 4C orchestrator (which carries
    its own enabled flag). 4D owns no policy boolean.
    """

    def __init__(
        self,
        *,
        start_result_service: ExecutionStartResultService,
        projection_orchestrator: ExecutionStateProjectionOrchestrator,
    ) -> None:
        self._start_result_service = start_result_service
        self._projection_orchestrator = projection_orchestrator

    def run_post_launch(self, launch_attempt_id: str) -> PostLaunchExecutionResult:
        """Run the post-launch authority sequence for one launch attempt.

        See module docstring for the exact frozen flow. Returns a non-durable
        PostLaunchExecutionResult. Raises PostLaunchExecutionError when 4A
        reconciliation is non-definitive (no durable result to report). Propagates
        4A typed errors and 4B typed projection errors unchanged.
        """
        result = self._start_result_service.reconcile_start_result(
            launch_attempt_id)
        if result is None:
            raise PostLaunchExecutionError(
                f"reconciliation non-definitive for "
                f"launch_attempt_id={launch_attempt_id!r}; no durable "
                f"ExecutionStartResult to report")

        if result.outcome == ExecutionStartOutcome.FAILED:
            return PostLaunchExecutionResult(
                launch_attempt_id=launch_attempt_id,
                status=PostLaunchStatus.FAILED_RECORDED,
                start_result=result,
                projection=None,
            )

        # result.outcome == STARTED (the only other definitive persisted outcome).
        try:
            projection = self._projection_orchestrator.project_executing_for_started(
                launch_attempt_id)
        except ExecutionStateProjectionDisabledError:
            return PostLaunchExecutionResult(
                launch_attempt_id=launch_attempt_id,
                status=PostLaunchStatus.STARTED_NOT_PROJECTED,
                start_result=result,
                projection=None,
            )
        # 4B conflict/integrity/ineligible errors propagate unchanged (NOT
        # converted to STARTED_NOT_PROJECTED).
        return PostLaunchExecutionResult(
            launch_attempt_id=launch_attempt_id,
            status=PostLaunchStatus.STARTED_PROJECTED,
            start_result=result,
            projection=projection,
        )
