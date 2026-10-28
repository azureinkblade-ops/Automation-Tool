"""PASS_CPU P0: I2V backend registry + Wan scaffolding (no GPU)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.i2v_backend_registry import (
    BACKEND_ID_SVD_XT_1_1,
    BACKEND_ID_WAN_22,
    DEFAULT_I2V_BACKEND,
    LIVE_PUBLISH,
    UnsupportedBackend,
    assert_backend_ready_for_generate,
    assert_no_svd_wan_coresident,
    assert_shadow_path_inert,
    document_exclusive_i2v_gpu_policy,
    get_i2v_backend,
    get_registration,
    i2v_backend_packet_field,
    is_i2v_wan_shadow_enabled,
    is_registered,
    parse_env_bool,
    registered_backend_ids,
    resolve_backend_for_generate,
    shadow_must_not_flip_media_outcome,
    wan_media_validity_hook_required,
)
from tools.i2v_production_adapter import (
    BACKEND_ID_SVD_XT_1_1 as ADAPTER_SVD,
    ImageToVideoAdapter,
    SourceImageRef,
    ValidationStatus,
    VideoJobStore,
    reset_default_gpu_lease,
)


@pytest.fixture(autouse=True)
def _reset_lease():
    reset_default_gpu_lease()
    yield
    reset_default_gpu_lease()


@pytest.fixture
def store(tmp_path: Path) -> VideoJobStore:
    return VideoJobStore(tmp_path / "i2v_jobs")


def _approved(**kwargs) -> SourceImageRef:
    base = dict(
        source_image_sha256="a" * 64,
        image_generation_complete=True,
        image_validation_complete=True,
        image_source_approved=True,
        source_width=768,
        source_height=1344,
        source_character_intent="CHARACTER",
        source_character_id_or_na="kai",
    )
    base.update(kwargs)
    return SourceImageRef(**base)


class FakeGpu:
    def __init__(self, free_mib: int = 14000, total_mib: int = 16376):
        self._free = free_mib
        self._total = total_mib

    def free_vram_mib(self) -> int:
        return self._free

    def total_vram_mib(self) -> int:
        return self._total


class FakeTransport:
    def __init__(self):
        self.workflows = []
        self.free_calls = 0

    def health_check(self) -> bool:
        return True

    def free_models(self):
        self.free_calls += 1
        return {"status_code": 200}

    def reconcile_prompt(self, prompt_id):
        return None

    def submit_and_wait(self, workflow):
        self.workflows.append(workflow)
        return {
            "video_bytes": b"video-bytes-ok",
            "video_path": "/tmp/out.mp4",
            "prompt_id": "p0",
        }


# --- Registry / env ---


def test_svd_is_default_constant():
    assert DEFAULT_I2V_BACKEND == BACKEND_ID_SVD_XT_1_1 == "svd_xt_1_1"
    assert ADAPTER_SVD == BACKEND_ID_SVD_XT_1_1
    assert get_registration(BACKEND_ID_SVD_XT_1_1).selectable_as_default is True
    assert get_registration(BACKEND_ID_SVD_XT_1_1).implementation_ready is True


def test_wan_registered_but_not_default_or_ready():
    assert is_registered(BACKEND_ID_WAN_22)
    assert BACKEND_ID_WAN_22 in registered_backend_ids()
    reg = get_registration(BACKEND_ID_WAN_22)
    assert reg is not None
    assert reg.selectable_as_default is False
    assert reg.implementation_ready is False


def test_env_default_svd(monkeypatch):
    monkeypatch.delenv("I2V_BACKEND", raising=False)
    assert get_i2v_backend() == BACKEND_ID_SVD_XT_1_1
    assert get_i2v_backend({}) == BACKEND_ID_SVD_XT_1_1


def test_env_i2v_backend_reads(monkeypatch):
    monkeypatch.setenv("I2V_BACKEND", BACKEND_ID_WAN_22)
    assert get_i2v_backend() == BACKEND_ID_WAN_22


def test_shadow_flag_parses_false_by_default(monkeypatch):
    monkeypatch.delenv("I2V_WAN_SHADOW", raising=False)
    assert is_i2v_wan_shadow_enabled() is False
    assert is_i2v_wan_shadow_enabled({}) is False
    assert parse_env_bool(None, default=False) is False
    assert parse_env_bool("", default=False) is False
    assert parse_env_bool("0", default=True) is False
    assert parse_env_bool("false", default=True) is False


def test_shadow_flag_truthy(monkeypatch):
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    assert is_i2v_wan_shadow_enabled() is True
    monkeypatch.setenv("I2V_WAN_SHADOW", "true")
    assert is_i2v_wan_shadow_enabled() is True


def test_packet_reports_i2v_backend():
    assert i2v_backend_packet_field(BACKEND_ID_SVD_XT_1_1) == "I2V_BACKEND=svd_xt_1_1"
    assert i2v_backend_packet_field(BACKEND_ID_WAN_22) == "I2V_BACKEND=wan_22"


def test_live_publish_gate_no():
    assert LIVE_PUBLISH == "NO"


def test_unknown_backend_rejected():
    with pytest.raises(UnsupportedBackend) as ei:
        assert_backend_ready_for_generate("not_a_real_backend")
    assert "unsupported backend_id=" in str(ei.value)


def test_wan_generate_resolve_fails_closed_without_p1():
    with pytest.raises(UnsupportedBackend) as ei:
        resolve_backend_for_generate(BACKEND_ID_WAN_22)
    msg = str(ei.value)
    assert "P1" in msg
    assert "wan_22" in msg


def test_wan_shadow_flag_does_not_unlock_generate(monkeypatch):
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    monkeypatch.setenv("I2V_BACKEND", BACKEND_ID_WAN_22)
    with pytest.raises(UnsupportedBackend):
        resolve_backend_for_generate(None)


def test_svd_resolve_ok():
    assert resolve_backend_for_generate(BACKEND_ID_SVD_XT_1_1) == BACKEND_ID_SVD_XT_1_1


def test_coresident_guard():
    assert_no_svd_wan_coresident(None, BACKEND_ID_WAN_22)  # ok
    with pytest.raises(UnsupportedBackend):
        assert_no_svd_wan_coresident(BACKEND_ID_SVD_XT_1_1, BACKEND_ID_WAN_22)
    policy = document_exclusive_i2v_gpu_policy()
    assert "KIND_I2V" in policy
    assert "co-resident" in policy


def test_shadow_must_not_flip_or_publish():
    assert shadow_must_not_flip_media_outcome() is True
    assert wan_media_validity_hook_required() is True
    assert_shadow_path_inert()
    with pytest.raises(UnsupportedBackend):
        assert_shadow_path_inert(proposed_media_outcome="SOCIAL_READY")
    with pytest.raises(UnsupportedBackend):
        assert_shadow_path_inert(enqueue_live_post=True)


# --- Adapter wiring ---


def test_adapter_svd_default_still_works(store):
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu()
    )
    result = adapter.generate_video(_approved(), seed=3, workflow_id="wf-p0-svd")
    assert result.backend_id == BACKEND_ID_SVD_XT_1_1
    assert result.validation_status == ValidationStatus.PASS.value
    assert "unsupported" not in (result.failure_reason or "")
    assert "P1" not in (result.failure_reason or "")
    assert len(transport.workflows) >= 1


def test_adapter_unknown_backend_rejected(store):
    adapter = ImageToVideoAdapter(
        store=store, transport=FakeTransport(), gpu_metrics=FakeGpu()
    )
    result = adapter.generate_video(
        _approved(), seed=1, backend_id="totally_unknown", workflow_id="wf-unk"
    )
    assert result.validation_status == ValidationStatus.INFRA_FAILURE.value
    assert result.state == "FAILED"
    assert "unsupported backend_id=totally_unknown" in (result.failure_reason or "")
    assert result.backend_id == "totally_unknown"
    assert i2v_backend_packet_field(result.backend_id) == "I2V_BACKEND=totally_unknown"


def test_adapter_wan_fails_closed_not_social_ready(store):
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu()
    )
    result = adapter.generate_video(
        _approved(),
        seed=1,
        backend_id=BACKEND_ID_WAN_22,
        workflow_id="wf-wan-p0",
    )
    assert result.validation_status == ValidationStatus.INFRA_FAILURE.value
    assert result.state == "FAILED"
    assert result.backend_id == BACKEND_ID_WAN_22
    assert "P1" in (result.failure_reason or "")
    # No fake success / no transport submit
    assert len(transport.workflows) == 0
    # Not a ready/social outcome
    assert result.video_sha256 is None
    assert result.video_path is None
