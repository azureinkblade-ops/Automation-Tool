"""First real governance consumer (read-only status query).

This module is the first narrow production-facing consumer of the Hermes
deterministic governance runtime. It sits between application orchestration and
the runtime provider (:func:`tools.hermes_core.runtime.get_governance_store`)
and answers ONE question: what is the authoritative governance status of a task?

Architectural invariant (absolute):

    ACCEPTED != EXECUTION AUTHORIZATION

This consumer reads governance truth only. It never transitions state, never
launches a worker, never creates or implies execution authorization, and never
touches ``automation_state.db``. The execution-authorization subsystem does not
yet exist; therefore ``can_authorize_execution`` is a hard architectural
declaration of ``False``, NOT a value derived from governance state. Logic
equivalent to ``can_authorize_execution = (state == "ACCEPTED")`` is forbidden.

Integrity is fail-closed: if loading authoritative governance state detects
tampering/corruption, the underlying ``GovernanceIntegrityError`` propagates.
It is deliberately NOT converted into an ordinary ``accepted = False`` business
miss, because a corrupted store and an un-reviewed task are different facts and
must remain distinguishable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tools.hermes_core.runtime import get_governance_chain
from tools.hermes_core.governance_store import GovernanceIntegrityError

# Hard architectural declaration: there is no execution-authorization subsystem
# in this milestone. Accepted governance is acceptance ONLY.
CAN_AUTHORIZE_EXECUTION: bool = False

ACCEPTED_STATE = "ACCEPTED"


@dataclass(frozen=True)
class TaskGovernanceStatus:
    """Read-only governance status for a task.

    The API makes the boundary visible: ``accepted`` and
    ``can_authorize_execution`` are distinct fields. A task can be accepted
    (``accepted = True``) while still having ``can_authorize_execution = False``.
    """

    task_id: str
    governance_state: Optional[str]
    accepted: bool
    can_authorize_execution: bool = CAN_AUTHORIZE_EXECUTION

    def __post_init__(self) -> None:
        # Guard the invariant even if a caller constructs the dataclass
        # directly: this milestone never authorizes execution.
        if self.can_authorize_execution:
            raise ValueError(
                "can_authorize_execution must be False in this milestone; "
                "no execution-authorization subsystem exists."
            )


def get_task_governance_status(task_id: str) -> TaskGovernanceStatus:
    """Return the authoritative governance status for a task.

    Args:
        task_id: the task identifier whose governance status is queried.

    Returns:
        A :class:`TaskGovernanceStatus` with the current ``governance_state``,
        whether the task is ``ACCEPTED`` (``accepted``), and
        ``can_authorize_execution = False`` (architectural declaration).

    Raises:
        GovernanceIntegrityError: if the authoritative store detects tampering
            or corruption. This is fail-closed and is NOT downgraded to a
            business-state miss.
    """
    # Reading through the runtime provider. No state transition, no worker,
    # no execution authorization. A single load gives both the state and the
    # acceptance fact; if the authoritative store is tampered, load raises
    # GovernanceIntegrityError and it propagates (fail-closed).
    chain = get_governance_chain(task_id)
    accepted = chain.governance_state == ACCEPTED_STATE
    return TaskGovernanceStatus(
        task_id=task_id,
        governance_state=chain.governance_state,
        accepted=accepted,
        can_authorize_execution=CAN_AUTHORIZE_EXECUTION,
    )
