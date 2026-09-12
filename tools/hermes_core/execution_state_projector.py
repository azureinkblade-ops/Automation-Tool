"""Authority-side execution-state projector (EA-4D.4B).

Consumes ONLY durable, hash-verified EA-4D.4A evidence from the Execution
Start DB and projects an immutable ``ExecutionStateProjection`` (target
EXECUTING) into the Authority DB. It performs NO runtime work:

* no subprocess / Popen / network / HTTP,
* no RuntimeLaunchAdapter.launch / RuntimeStartLookup.lookup,
* no route reselection / new LaunchAttempt / StartResult mutation,
* no default real-coordinator enablement.

The projector is the ONLY component that may create an EXECUTING projection.
It is invoked explicitly (Option A): ``ExecutionStartResult`` persistence
(4A) does NOT implicitly project EXECUTING. The Authority DB's effective
state is *derived* from the committed, immutable projection; the
``ExecutionAttempt.status`` remains ``RECORDED`` forever.

Four-way boundary (frozen):

    LAUNCH_ATTEMPT_RECORDED
    != WORKER STARTED
    != ExecutionStartResult persisted
    != EXECUTING

This module owns the final step only.
"""

from __future__ import annotations

from typing import Optional

from .execution_authorization import (
    ExecutionStateProjection,
    ExecutionStateProjectionConflictError,
    ExecutionStateProjectionIneligibleError,
    build_execution_state_projection,
)
from .execution_start import ExecutionStartOutcome
from .sqlite_execution_start_store import (
    SQLiteExecutionStartStore,
    ExecutionStartIntegrityError,
)
from .sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)


class ExecutionStateProjector:
    """Projects a verified STARTED result into an immutable EXECUTING projection.

    The projector is constructed with the durable Start DB store and the
    Authority DB store. ``project_executing(launch_attempt_id)`` loads the
    persisted ``ExecutionStartResult`` + verified launch-attempt lineage,
    validates STARTED-only eligibility and integrity, builds the deterministic
    immutable projection, and persists it (idempotent / conflict-safe).
    """

    def __init__(
        self,
        start_store: SQLiteExecutionStartStore,
        authority_store: SQLiteExecutionAuthorizationStore,
    ) -> None:
        self._start_store = start_store
        self._authority_store = authority_store

    def project_executing(self, launch_attempt_id: str) -> ExecutionStateProjection:
        """Project EXECUTING for a verified, durably persisted STARTED result.

        Raises ``ExecutionStateProjectionIneligibleError`` when no result exists,
        the result is not STARTED, the result hash is invalid, ``runtime_run_id``
        is empty, or authority lineage is missing. Raises
        ``ExecutionStateProjectionConflictError`` on a conflicting committed
        projection. Raises an integrity error on tampered input.
        """
        result = self._start_store.get_execution_start_result(launch_attempt_id)
        if result is None:
            raise ExecutionStateProjectionIneligibleError(
                f"no persisted ExecutionStartResult for "
                f"launch_attempt_id={launch_attempt_id!r}; not eligible")

        if result.outcome != ExecutionStartOutcome.STARTED:
            raise ExecutionStateProjectionIneligibleError(
                f"result outcome {result.outcome!r} is not STARTED; "
                f"EXECUTING projection refused")

        if not getattr(result, "verify_hash", lambda: False)():
            raise ExecutionStateProjectionIneligibleError(
                f"persisted result for launch_attempt_id={launch_attempt_id!r} "
                f"failed hash verification; refusing projection")

        if not result.runtime_run_id:
            raise ExecutionStateProjectionIneligibleError(
                f"STARTED result has empty runtime_run_id; not eligible")

        if not result.runtime_evidence_hash:
            raise ExecutionStateProjectionIneligibleError(
                f"STARTED result missing runtime_evidence_hash; not eligible")

        attempt = self._start_store.get_execution_launch_attempt(launch_attempt_id)
        if attempt is None:
            raise ExecutionStateProjectionIneligibleError(
                f"no verified launch-attempt lineage for "
                f"launch_attempt_id={launch_attempt_id!r}; not eligible")
        if not attempt.verify_hash():
            raise ExecutionStartIntegrityError(
                f"launch-attempt lineage for launch_attempt_id="
                f"{launch_attempt_id!r} failed hash verification")

        # Authority-lineage recheck: required fields must be present and
        # non-empty after hash verification (EA-4D.4B §35). These are bound in
        # the verified launch-attempt canonical_json (Option A exposure).
        for field in (
            "authorization_id", "authorization_hash",
            "attempt_id", "attempt_hash",
            "reservation_hash", "route_id", "route_hash",
        ):
            if not getattr(attempt, field, None):
                raise ExecutionStateProjectionIneligibleError(
                    f"launch-attempt lineage missing {field}; not eligible")

        projection = build_execution_state_projection(
            start_result_id=result.start_result_id,
            start_result_hash=result.artifact_hash,
            launch_attempt_id=attempt.launch_attempt_id,
            launch_attempt_hash=attempt.launch_attempt_hash,
            route_id=attempt.route_id,
            route_hash=attempt.route_hash,
            authorization_id=attempt.authorization_id,
            authorization_hash=attempt.authorization_hash,
            attempt_id=attempt.attempt_id,
            attempt_hash=attempt.attempt_hash,
            task_id=attempt.task_id,
            worker_id=attempt.worker_id,
            worker_version=attempt.worker_version,
            runtime_run_id=result.runtime_run_id,
        )

        self._authority_store.record_projection(projection)
        return projection
