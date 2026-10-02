from dataclasses import replace

import pytest

from tools import regional_hand_repair as rhr
from tools import spatial_guide as sg
from tools.image_pipeline_v2_assets import resolve_asset
from tools.realistic_pipeline_v2 import RealisticPipelineV2
from tools.regional_hand_repair_contract import (
    build_canonical_task_input_envelope,
    canonical_json_bytes,
    canonical_task_input_sha256,
)


@pytest.fixture(scope="module")
def repair_request():
    spec = RealisticPipelineV2().build_spec(
        novel="en",
        chapter="ch1",
        scene_text=None,
        studio_bible_enrich=True,
        prompt="weekend promo, cinematic",
        seed=1_000_003,
    )
    guide_request = sg.build_spatial_guide_request_from_spec(
        spec, novel="EN", seed=1_000_003
    )
    params = sg.en_sanctioned_hand_interaction_params()
    pose = sg.derive_normalized_pose(guide_request, hand_interaction=params)
    region = rhr.derive_hand_repair_region(
        pose.hands[0],
        guide_request.contact_regions[0],
        subject=guide_request.subject_regions[0],
        blade=guide_request.object_regions[0],
        image_width=1024,
        image_height=1024,
    )
    mask = rhr.render_hand_repair_mask(region)
    checkpoint = resolve_asset("sdxl_base_1.0")
    lora = resolve_asset("lora_realistic_posts")
    return rhr.RepairRequest(
        source_image_sha256="a" * 64,
        hand_guide_sha256="b" * 64,
        structural_request_sha256="c" * 64,
        repair_region=region,
        repair_mask_sha256=rhr.repair_mask_sha256(mask),
        repair_prompt=rhr.REPAIR_POSITIVE_CONDITIONING,
        repair_negative_prompt=rhr.REPAIR_NEGATIVE_CONDITIONING,
        repair_seed=rhr.derive_repair_seed("a" * 64),
        sampler=rhr.REPAIR_DEFAULT_SAMPLER,
        scheduler=rhr.REPAIR_DEFAULT_SCHEDULER,
        steps=rhr.REPAIR_DEFAULT_STEPS,
        cfg=rhr.REPAIR_DEFAULT_CFG,
        denoise=rhr.REPAIR_DEFAULT_DENOISE,
        checkpoint_asset_id=checkpoint.asset_id,
        checkpoint_reference=checkpoint.comfyui_reference,
        checkpoint_sha256=checkpoint.sha256,
        lora_asset_id=lora.asset_id,
        lora_reference=lora.comfyui_reference,
        lora_sha256=lora.sha256,
        lora_strength=0.85,
        source_primary_execution_id="v2exec-realistic-0000",
    )


def _envelope(repair_request):
    return build_canonical_task_input_envelope(
        repair_request,
        source_width=1024,
        source_height=1024,
        workflow_template_sha256="d" * 64,
        allowed_node_set_sha256="e" * 64,
    )


def test_repair_request_identity_excludes_transport_paths(repair_request):
    a = replace(
        repair_request,
        source_image_path=r"C:\\host-a\\source.png",
        hand_guide_reference=r"C:\\host-a\\guide.png",
    )
    b = replace(
        repair_request,
        source_image_path=r"D:\\host-b\\source.png",
        hand_guide_reference=r"D:\\host-b\\guide.png",
    )
    assert a.identity_payload() != b.identity_payload()
    assert a.hash_preimage() == b.hash_preimage()
    assert "source_image_path" not in a.hash_preimage()
    assert "hand_guide_reference" not in a.hash_preimage()
    assert a.sha256() == b.sha256()


def test_canonical_envelope_has_fixed_decimals_and_explicit_optionals(repair_request):
    envelope = _envelope(repair_request)
    assert envelope["sampling"]["cfg"] == "4.50000000"
    assert envelope["sampling"]["denoise"] == "0.58000000"
    assert all(len(value.split(".")[1]) == 8 for value in envelope["repair_region"]["rect_normalized"])
    assert envelope["ip_adapter"] is None
    assert envelope["controlnet"] is None
    assert b"source_image_path" not in canonical_json_bytes(envelope)


def test_canonical_envelope_is_path_and_provenance_independent(repair_request):
    a = replace(
        repair_request,
        source_primary_execution_id="v2exec-host-a",
        source_image_path=r"C:\\a\\source.png",
        hand_guide_reference=r"C:\\a\\guide.png",
    )
    b = replace(
        repair_request,
        source_primary_execution_id="v2exec-host-b",
        source_image_path=r"D:\\b\\source.png",
        hand_guide_reference=r"D:\\b\\guide.png",
    )
    assert canonical_task_input_sha256(_envelope(a)) == canonical_task_input_sha256(
        _envelope(b)
    )


def test_canonical_envelope_golden_vector(repair_request):
    assert canonical_task_input_sha256(_envelope(repair_request)) == (
        "461f3b323f8dd1f6513deed7ec3fc54692f87eaf0337750a52d2aac1c4faa910"
    )
