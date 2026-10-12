"""Default-disabled delegated text-process owner; no concrete controller wired."""

from dataclasses import dataclass

from tools.hermes_core.agent_delegated_claim_owner import AgentDelegatedClaimOwner
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_ping_command import AgentTextPingCommand
from tools.hermes_core.agent_text_process_observation import (
    SQLiteAgentTextProcessObservationStore,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.governed_bound_executor import GovernedExecutorResolution
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
)


@dataclass(frozen=True)
class TextProcessStarted:
    owner_id: str
    pid: int


@dataclass(frozen=True)
class TextProcessFinished:
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes


@dataclass(frozen=True)
class TextProcessOwnerState:
    status: str
    reason: str
    start_hash: str | None = None
    terminal_hash: str | None = None


class AgentTextProcessOwner:
    """One in-flight caller may report facts; replay never starts a process."""

    def __init__(self, claim_owner: AgentDelegatedClaimOwner,
                 observations: SQLiteAgentTextProcessObservationStore,
                 *, controller=None):
        if (type(claim_owner) is not AgentDelegatedClaimOwner
                or type(observations) is not SQLiteAgentTextProcessObservationStore
                or claim_owner.bridge_store is not observations.intents.bridge_store
                or claim_owner.fence_store is not observations.fences):
            raise DelegationIntegrityError("text process owner stores denied")
        self.claim_owner = claim_owner
        self.observations = observations
        self.controller = controller

    def _contain(self, started: TextProcessStarted) -> bool:
        try:
            self.controller.kill(started)
        except Exception:
            return False
        return True

    def execute_once(
        self, plan: AgentTextPingCommand,
        resolution: GovernedExecutorResolution,
        authorization: ProductionInvocationAuthorization,
    ) -> TextProcessOwnerState:
        """Claim and report once. An injected controller is required to do work."""
        if type(plan) is not AgentTextPingCommand:
            return TextProcessOwnerState("DENIED", "INVALID_PROCESS_PLAN")
        attempt_id = plan.attempt_id
        prior = self.observations.get_start(attempt_id)
        if prior is not None:
            if prior.argv_hash != plan.argv_hash:
                return TextProcessOwnerState("DENIED", "PROCESS_PLAN_COMMAND_MISMATCH")
            terminal = self.observations.get_terminal(attempt_id)
            return TextProcessOwnerState(
                "RECONCILE_ONLY", "PROCESS_ALREADY_REPORTED",
                start_hash=prior.start_hash,
                terminal_hash=terminal.terminal_hash if terminal else None,
            )
        if self.observations.fences.get(attempt_id) is not None:
            return TextProcessOwnerState("UNKNOWN", "START_FENCE_ALREADY_CLAIMED")
        if self.controller is None:
            return TextProcessOwnerState("DENIED", "NO_PROCESS_CONTROLLER")
        if any(not callable(getattr(self.controller, name, None))
               for name in ("prepare", "start", "wait", "kill")):
            return TextProcessOwnerState("DENIED", "INVALID_PROCESS_CONTROLLER")
        witness = load_bound_agent_start(
            self.claim_owner.bridge_store.authority,
            self.claim_owner.bridge_store.start,
            attempt_id,
        )
        bridge = self.claim_owner.bridge_store.get(attempt_id)
        if (bridge is None or plan.bridge_hash != bridge.artifact_hash
                or plan.receiver_agent_id != witness.receipt.receiver_agent_id
                or plan.task_input_hash != witness.task.task_input_hash
                or plan.runtime_run_id != witness.bound.invocation.runtime_run_id):
            return TextProcessOwnerState("DENIED", "PROCESS_PLAN_LINEAGE_MISMATCH")
        try:
            qualified_plan = self.controller.prepare(witness, bridge)
        except Exception:
            return TextProcessOwnerState("DENIED", "PROCESS_PLAN_QUALIFICATION_FAILED")
        if type(qualified_plan) is not AgentTextPingCommand or qualified_plan != plan:
            return TextProcessOwnerState("DENIED", "PROCESS_PLAN_NOT_QUALIFIED")
        intent = self.observations.intents.verify_command(attempt_id, plan.argv)
        if intent.argv_hash != plan.argv_hash:
            return TextProcessOwnerState("DENIED", "PROCESS_PLAN_COMMAND_MISMATCH")
        claim = self.claim_owner.claim_and_fence(
            attempt_id, resolution, authorization,
        )
        if claim.status != "FENCED":
            return TextProcessOwnerState(claim.status, claim.reason)
        fence = self.observations.fences.get(attempt_id)
        if (claim.fence_hash is None or fence is None
                or fence.claim_hash != claim.fence_hash):
            return TextProcessOwnerState("UNKNOWN", "START_FENCE_UNCERTAIN")
        try:
            started = self.controller.start(plan.argv)
        except Exception:
            return TextProcessOwnerState("UNKNOWN", "PROCESS_START_UNCERTAIN")
        if (type(started) is not TextProcessStarted
                or type(started.owner_id) is not str or not started.owner_id
                or type(started.pid) is not int or started.pid <= 0):
            return TextProcessOwnerState("UNKNOWN", "PROCESS_START_REPORT_INVALID")
        try:
            start = self.observations.record_start(
                attempt_id, plan.argv, owner_id=started.owner_id,
                pid=started.pid,
            )
        except Exception:
            kill_requested = self._contain(started)
            return TextProcessOwnerState(
                "UNKNOWN", "START_REPORT_FAILED_KILL_REQUESTED" if kill_requested
                else "START_REPORT_FAILED_KILL_UNCERTAIN",
            )
        try:
            finished = self.controller.wait(started)
        except Exception:
            kill_requested = self._contain(started)
            return TextProcessOwnerState(
                "UNKNOWN", "TERMINAL_WAIT_FAILED_KILL_REQUESTED" if kill_requested
                else "TERMINAL_WAIT_FAILED_KILL_UNCERTAIN",
                start_hash=start.start_hash,
            )
        if type(finished) is not TextProcessFinished:
            self._contain(started)
            return TextProcessOwnerState(
                "UNKNOWN", "TERMINAL_REPORT_INVALID", start_hash=start.start_hash,
            )
        try:
            terminal = self.observations.record_terminal(
                attempt_id, owner_id=started.owner_id, pid=started.pid,
                returncode=finished.returncode,
                stdout_bytes=finished.stdout_bytes,
                stderr_bytes=finished.stderr_bytes,
            )
        except Exception:
            return TextProcessOwnerState(
                "UNKNOWN", "TERMINAL_REPORT_UNCERTAIN", start_hash=start.start_hash,
            )
        return TextProcessOwnerState(
            "REPORTED_TERMINAL", "NO_TRUSTED_CAPTURE",
            start_hash=start.start_hash, terminal_hash=terminal.terminal_hash,
        )
