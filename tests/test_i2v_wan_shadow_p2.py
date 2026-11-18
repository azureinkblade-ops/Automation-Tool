"""P2: I2V_WAN_SHADOW GPU shadow — sequential ExclusiveGpuLease, non-canon."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.i2v_backend_registry import (
    BACKEND_ID_SVD_XT_1_1,
    BACKEND_ID_WAN_22,
    LIVE_PUBLISH,
    UnsupportedBackend,
    assert_no_svd_wan_coresident,
    assert_shadow_path_inert,
    is_i2v_wan_shadow_enabled,
    should_run_wan_shadow,
    wan_shadow_artifact_dir,
)
from tools.i2v_production_adapter import (
    ExclusiveGpuLease,
    GpuOwnershipConflict,
    ImageToVideoAdapter,
    SourceImageRef,
    ValidationStatus,
    VIDEO_CREATES_IDENTITY_CANON,
    VideoJobStore,
    reset_default_gpu_lease,
)
from tools.media_validity import pass_probe_for_tests


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
        source_image_sha256="b" * 64,
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
        # >10KB fake mp4 payload
        return {
            "video_bytes": b"V" * 12000,
            "video_path": None,
            "prompt_id": f"p-shadow-{len(self.workflows)}",
        }


def test_should_run_wan_shadow_gate(monkeypatch):
    monkeypatch.delenv("I2V_WAN_SHADOW", raising=False)
    assert should_run_wan_shadow(BACKEND_ID_SVD_XT_1_1) is False
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    assert should_run_wan_shadow(BACKEND_ID_SVD_XT_1_1) is True
    assert should_run_wan_shadow(BACKEND_ID_WAN_22) is False


def test_shadow_off_leaves_wan_shadow_none(store, monkeypatch):
    monkeypatch.delenv("I2V_WAN_SHADOW", raising=False)
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu()
    )
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-p2-off")
    assert result.backend_id == BACKEND_ID_SVD_XT_1_1
    assert result.validation_status == ValidationStatus.PASS.value
    assert result.wan_shadow is None
    # Only SVD workflow submitted (no Wan shadow graph)
    assert len(transport.workflows) == 1
    assert "Wan22ImageToVideoLatent" not in str(transport.workflows[0])


def test_shadow_on_runs_wan_after_svd_noncanon(store, monkeypatch):
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    assert is_i2v_wan_shadow_enabled() is True
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu()
    )
    result = adapter.generate_video(
        _approved(),
        seed=2,
        workflow_id="wf-p2-on",
        motion_plan={"positive_prompt": "scenery only misty forest"},
    )
    # Primary unchanged
    assert result.backend_id == BACKEND_ID_SVD_XT_1_1
    assert result.validation_status == ValidationStatus.PASS.value
    assert result.state == "READY"
    assert result.video_creates_identity_canon is False
    assert VIDEO_CREATES_IDENTITY_CANON is False
    assert LIVE_PUBLISH == "NO"
    # Shadow packet
    assert result.wan_shadow is not None
    assert result.wan_shadow["shadow"] is True
    assert result.wan_shadow["backend_id"] == BACKEND_ID_WAN_22
    assert result.wan_shadow["video_creates_identity_canon"] is False
    assert result.wan_shadow["media_outcome_flipped"] is False
    assert result.wan_shadow["live_publish"] == "NO"
    assert result.wan_shadow["status"] == "PASS"
    assert result.wan_shadow["media_validity_ok"] is True
    # SVD then Wan workflows; /free between (>=2 free calls: pre SVD + between + after shadow)
    assert len(transport.workflows) == 2
    wan_wf = transport.workflows[1]
    assert wan_wf["55"]["class_type"] == "Wan22ImageToVideoLatent"
    assert transport.free_calls >= 2
    # Artifacts under shadow dir
    art = Path(result.wan_shadow["artifact_dir"])
    assert art.is_dir()
    assert (art / "shadow_packet.json").is_file()
    assert (art / "workflow.json").is_file()


def test_shadow_does_not_flip_social_ready(monkeypatch):
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    with pytest.raises(UnsupportedBackend):
        assert_shadow_path_inert(proposed_media_outcome="SOCIAL_READY")
    with pytest.raises(UnsupportedBackend):
        assert_shadow_path_inert(enqueue_live_post=True)


def test_lease_blocks_svd_wan_coresident(monkeypatch):
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    lease = ExclusiveGpuLease()
    lease.acquire(
        "svd-job",
        ExclusiveGpuLease.KIND_I2V,
        backend_id=BACKEND_ID_SVD_XT_1_1,
    )
    assert lease.active_backend_id() == BACKEND_ID_SVD_XT_1_1
    with pytest.raises(GpuOwnershipConflict) as ei:
        lease.acquire(
            "wan-job",
            ExclusiveGpuLease.KIND_I2V,
            backend_id=BACKEND_ID_WAN_22,
        )
    assert "co-resident" in str(ei.value) or "owned by" in str(ei.value)
    with pytest.raises(UnsupportedBackend):
        assert_no_svd_wan_coresident(BACKEND_ID_SVD_XT_1_1, BACKEND_ID_WAN_22)


def test_shadow_failure_does_not_fail_primary(store, monkeypatch):
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")

    class BoomTransport(FakeTransport):
        def submit_and_wait(self, workflow):
            if any(
                isinstance(n, dict) and n.get("class_type") == "Wan22ImageToVideoLatent"
                for n in workflow.values()
            ):
                self.workflows.append(workflow)
                raise RuntimeError("wan boom")
            return FakeTransport.submit_and_wait(self, workflow)

    transport = BoomTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu()
    )
    result = adapter.generate_video(_approved(), seed=3, workflow_id="wf-p2-boom")
    assert result.validation_status == ValidationStatus.PASS.value
    assert result.backend_id == BACKEND_ID_SVD_XT_1_1
    assert result.wan_shadow is not None
    assert result.wan_shadow["status"] == "FAIL"
    assert "wan boom" in (result.wan_shadow.get("failure_reason") or "")


def test_wan_shadow_artifact_dir_helper(tmp_path):
    d = wan_shadow_artifact_dir(tmp_path, "job-xyz")
    assert d.endswith(str(Path("wan_i2v_shadow") / "job-xyz")) or "wan_i2v_shadow" in d


def test_direct_run_wan_gpu_shadow_with_probe(store, monkeypatch, tmp_path):
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu()
    )
    primary = adapter.generate_video(_approved(), seed=4, workflow_id="wf-p2-direct")
    # turn shadow off for the primary call path by clearing packet and calling direct
    monkeypatch.setenv("I2V_WAN_SHADOW", "1")
    packet = adapter.run_wan_gpu_shadow(
        source_image=_approved(),
        primary_result=primary,
        seed=4,
        shadow_root=tmp_path / "shadow_root",
        media_validity_probe=pass_probe_for_tests(width=720, height=1280),
        motion_plan={"positive_prompt": "scenery only"},
    )
    assert packet["shadow"] is True
    assert packet["status"] == "PASS"
    assert packet["media_validity_ok"] is True
    assert Path(packet["artifact_dir"]).is_dir()
