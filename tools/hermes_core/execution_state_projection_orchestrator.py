"""EA-4D.4C trusted projection-policy orchestrator (mechanics slice).

This is the narrow, explicit integration boundary between EA-4D.4A durable
``ExecutionStartResult`` persistence and the EA-4D.4B ``ExecutionStateProjector``
API. It is POLICY-ONLY and deliberately thin:

* It checks an explicit ``enabled`` flag.
* When enabled, it invokes ``ExecutionStateProjector.project_executing(
  launch_attempt_id)`` exactly once for the request.
* It propagates the typed projector errors (conflict / integrity / ineligible)
  without reinterpreting them.

It does NOT:

* load or interpret the persisted ``ExecutionStartResult`` itself (EA-4D.4B is
  the authoritative STARTED-only reader/verifier);
* perform any runtime launch / lookup / subprocess / network;
* mutate routes, LaunchAttempts, StartResults, or ExecutionAttempts;
* create any new durable authority artifact (observability only).

Four-way boundary (frozen):

    LAUNCH_ATTEMPT_RECORDED
    != WORKER STARTED
    != ExecutionStartResult persisted
    != ExecutionStateProjection(EXECUTING) committed

This module owns the policy gate only. The durable eligibility/integrity/replay
logic stays in EA-4D.4B.

Default-off: ``enabled`` defaults to ``False``. With ``enabled is False`` the
orchestrator raises ``ExecutionStateProjectionDisabledError`` and the projector
is NEVER invoked (no authority mutation, no ledger append, STARTED unchanged).

No production, scheduler, or default-coordinator caller is wired in this slice.
Invocation is restricted to explicit trusted/manual/test orchestration. A later
governance slice may authorize an actual production caller.
"""

from __future__ import annotations

from typing import Optional

from .execution_state_projector import ExecutionStateProjector


class ExecutionStateProjectionDisabledError(Exception):
    """Raised when the 4C projection policy is disabled.

    Typed, non-runtime failure. The projector is NOT invoked; no authority
    mutation and no ledger append occur; the persisted STARTED result is
    unchanged. This is the ONLY disabled outcome (no sentinel-return path).
    """


class ExecutionStateProjectionOrchestrator:
    """Policy-only bridge that invokes the 4B projector when enabled.

    Construction is explicit and trusted: the caller supplies an already-built
    ``ExecutionStateProjector`` and an ``enabled`` policy flag (default False).
    """

    def __init__(
        self,
        *,
        projector: ExecutionStateProjector,
        enabled: bool = False,
    ) -> None:
        self._projector = projector
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def project_executing_for_started(
        self,
        launch_attempt_id: str,
    ) -> object:
        """Invoke the 4B projector for a STARTED result, if policy allows.

        Behavior:

        * ``enabled is False`` -> raise ``ExecutionStateProjectionDisabledError``
          (projector NOT invoked).
        * ``enabled is True`` -> delegate to
          ``ExecutionStateProjector.project_executing(launch_attempt_id)``.

        The orchestrator does NOT independently verify STARTED eligibility; the
        projector authoritatively enforces it and raises typed
        ineligible/integrity/conflict errors, which this method propagates
        unchanged.
        """
        if not self._enabled:
            raise ExecutionStateProjectionDisabledError(
                f"execution state projection is disabled; not projecting "
                f"launch_attempt_id={launch_attempt_id!r}")
        return self._projector.project_executing(launch_attempt_id)
