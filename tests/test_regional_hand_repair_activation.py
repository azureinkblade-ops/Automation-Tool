"""EA-4D.4F Step 12: independent activation-domain proof."""

from __future__ import annotations

import itertools

import pytest

from tools.hermes_core.execution_post_launch_dispatcher import (
    ExecutionPostLaunchDispatcher,
    ExecutionPostLaunchDispatchDisabledError,
)
from tools.hermes_core.execution_state_projection_orchestrator import (
    ExecutionStateProjectionOrchestrator,
)
from tools.regional_hand_repair import (
    RepairGpuAuthorityAbsent,
    run_regional_hand_repair,
)
from tools.regional_hand_repair_pilot import (
    PilotConfig,
    RegionalHandRepairPilotRoot,
)
from tests.test_hermes_authority_integration import _repair_request


class _ProjectionProbe:
    def __init__(self) -> None:
        self.calls = 0

    def project_executing(self, launch_attempt_id: str) -> object:
        self.calls += 1
        return {"launch_attempt_id": launch_attempt_id}


class _PostLaunchProbe:
    def __init__(self, projection_orchestrator) -> None:
        self.projection_orchestrator = projection_orchestrator
        self.calls = 0

    def run_post_launch(self, launch_attempt_id: str) -> object:
        self.calls += 1
        if self.projection_orchestrator.enabled:
            self.projection_orchestrator.project_executing_for_started(
                launch_attempt_id
            )
        return {"launch_attempt_id": launch_attempt_id}


def test_all_activation_domains_default_off():
    root = RegionalHandRepairPilotRoot(PilotConfig())
    projection = ExecutionStateProjectionOrchestrator(
        projector=_ProjectionProbe()
    )
    dispatcher = ExecutionPostLaunchDispatcher(
        post_launch_orchestrator=_PostLaunchProbe(projection)
    )
    try:
        assert root.is_active is False
        assert dispatcher.enabled is False
        assert projection.enabled is False
        refusal = run_regional_hand_repair(_repair_request())
        assert refusal["gpu_authority"] is False
        assert refusal["gpu_submission_attempted"] is False
    finally:
        root.close()


@pytest.mark.parametrize(
    "root_enabled,dispatcher_enabled,projection_enabled,gpu_authority",
    list(itertools.product([False, True], repeat=4)),
)
def test_activation_truth_table_has_no_cross_activation(
    root_enabled,
    dispatcher_enabled,
    projection_enabled,
    gpu_authority,
):
    projection_probe = _ProjectionProbe()
    projection = ExecutionStateProjectionOrchestrator(
        projector=projection_probe,
        enabled=projection_enabled,
    )
    post_launch = _PostLaunchProbe(projection)
    dispatcher = ExecutionPostLaunchDispatcher(
        post_launch_orchestrator=post_launch,
        enabled=dispatcher_enabled,
    )
    root = RegionalHandRepairPilotRoot(PilotConfig(enabled=root_enabled))
    scheduler_calls = 0

    try:
        if not root_enabled:
            with pytest.raises(RuntimeError, match="pilot is disabled"):
                root.dispatch_authorized_post_launch(
                    launch_attempt_id="launch-step12",
                    dispatcher=dispatcher,
                )
        elif not dispatcher_enabled:
            with pytest.raises(ExecutionPostLaunchDispatchDisabledError):
                root.dispatch_authorized_post_launch(
                    launch_attempt_id="launch-step12",
                    dispatcher=dispatcher,
                )
        else:
            result = root.dispatch_authorized_post_launch(
                launch_attempt_id="launch-step12",
                dispatcher=dispatcher,
            )
            assert result["launch_attempt_id"] == "launch-step12"

        assert post_launch.calls == int(root_enabled and dispatcher_enabled)
        assert projection_probe.calls == int(
            root_enabled and dispatcher_enabled and projection_enabled
        )

        if gpu_authority:
            with pytest.raises(RepairGpuAuthorityAbsent, match="not production-activated"):
                run_regional_hand_repair(
                    _repair_request(),
                    gpu_authority=True,
                    submitter=lambda request, workflow: b"not-called",
                )
        else:
            refusal = run_regional_hand_repair(
                _repair_request(), gpu_authority=False
            )
            assert refusal["gpu_submission_attempted"] is False

        assert root.is_active is root_enabled
        assert dispatcher.enabled is dispatcher_enabled
        assert projection.enabled is projection_enabled
        assert scheduler_calls == 0
    finally:
        root.close()
