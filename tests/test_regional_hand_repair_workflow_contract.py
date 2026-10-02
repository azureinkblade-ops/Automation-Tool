import copy

import pytest

from tools.regional_hand_repair import build_regional_hand_repair_workflow
from tools.regional_hand_repair_workflow_contract import (
    RegionalHandRepairWorkflowContractError,
    validate_frozen_repair_workflow,
)
from tests.test_regional_hand_repair_contract import repair_request


def test_control_and_treatment_topologies_are_allowlisted(repair_request):
    control = build_regional_hand_repair_workflow(repair_request)
    # Treatment uses a different encode architecture via request field
    from dataclasses import replace
    treatment_request = replace(
        repair_request,
        repair_encode_architecture="vae_encode_set_latent_noise_mask"
    )
    treatment = build_regional_hand_repair_workflow(treatment_request)
    assert len(validate_frozen_repair_workflow(control)) == 64
    assert len(validate_frozen_repair_workflow(treatment)) == 64


@pytest.mark.parametrize(
    "mutation",
    [
        lambda wf: wf["nodes"].update(
            {"RX": {"class_type": "ControlNetApplyAdvanced", "inputs": {}}}
        ),
        lambda wf: wf["nodes"]["R7"].update({"class_type": "UnknownSampler"}),
        lambda wf: wf["v2_meta"].update({"whole_image_second_pass": True}),
        lambda wf: wf["v2_meta"].update({"openpose_controlnet_used": True}),
    ],
)
def test_unapproved_workflow_mutations_fail_closed(repair_request, mutation):
    workflow = copy.deepcopy(build_regional_hand_repair_workflow(repair_request))
    mutation(workflow)
    with pytest.raises(RegionalHandRepairWorkflowContractError):
        validate_frozen_repair_workflow(workflow)
