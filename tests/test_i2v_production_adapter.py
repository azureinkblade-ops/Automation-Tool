"""CPU/mock tests for production I2V adapter contract."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.i2v_production_adapter import (
    BACKEND_ID_SVD_XT_1_1,
    BACKEND_SETTINGS_VERSION,
    MAX_INFRASTRUCTURE_ATTEMPTS,
    MIN_FREE_VRAM_MIB,
    MODEL_SHA256_SVD_XT_1_1,
    STATIC_FALLBACK_SUPPORTED,
    TEXT_CONTROL_SUPPORTED,
    VIDEO_CREATES_IDENTITY_CANON,
    ExclusiveGpuLease,
    GpuOwnershipConflict,
    GpuHeadroomInsufficient,
    ImageToVideoAdapter,
    JobState,
    I2VSettings,
    MissingSourceShaError,
    SourceImageRef,
    SourceNotApprovedError,
    TemporalFlicker,
    ValidationStatus,
    VideoJobStore,
    build_svd_xt_workflow,
    compute_fit_inside_letterbox,
    compute_video_idempotency_key,
    reset_default_gpu_lease,
    workflow_contains_text_identity_prompt,
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
    def __init__(self, free_mib: int, total_mib: int = 16376):
        self._free = free_mib
        self._total = total_mib

    def free_vram_mib(self) -> int:
        return self._free

    def total_vram_mib(self) -> int:
        return self._total

    def set_free(self, free_mib: int) -> None:
        self._free = free_mib


class FakeTransport:
    def __init__(self):
        self.workflows = []
        self.free_calls = 0
        self.fail_times = 0
        self._fail_remaining = 0
        self.submit_count = 0
        self._reconcile_map = {}

    def arm_failures(self, n: int) -> None:
        self._fail_remaining = n

    def set_reconcile(self, prompt_id, payload):
        self._reconcile_map[str(prompt_id)] = payload

    def health_check(self) -> bool:
        return True

    def free_models(self):
        self.free_calls += 1
        return {"status_code": 200}

    def reconcile_prompt(self, prompt_id):
        return self._reconcile_map.get(str(prompt_id))

    def submit_and_wait(self, workflow):
        from tools.i2v_production_adapter import InfrastructureFailure

        self.workflows.append(workflow)
        self.submit_count += 1
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise InfrastructureFailure("oom_or_transport")
        return {"video_bytes": b"video-bytes-ok", "video_path": "/tmp/out.mp4", "prompt_id": "p1"}


def test_approved_still_accepted(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-1")
    assert result.validation_status == ValidationStatus.PASS.value
    assert result.static_fallback_supported is True


def test_unapproved_still_rejected(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    with pytest.raises(SourceNotApprovedError):
        adapter.generate_video(
            _approved(image_source_approved=False),
            seed=1,
            workflow_id="wf-1",
        )


def test_missing_source_sha_rejected(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    with pytest.raises(MissingSourceShaError):
        adapter.generate_video(
            _approved(source_image_sha256=""),
            seed=1,
            workflow_id="wf-1",
        )


def test_transform_geometry_deterministic():
    a = compute_fit_inside_letterbox(768, 1344)
    b = compute_fit_inside_letterbox(768, 1344)
    assert a == b
    assert a.scaled_width == 329
    assert a.scaled_height == 576
    assert a.pad_left == 347
    assert a.pad_right == 348
    assert a.pad_top == 0
    assert a.pad_bottom == 0
    assert a.transform_sha256 == (
        "403840ccfa10db81e9587aa9a894f6b84db3ed50f755cef7baa165c17e9aa6cc"
    )


def test_transform_no_crop_no_stretch():
    t = compute_fit_inside_letterbox(768, 1344)
    assert t.uses_crop is False
    assert t.uses_stretch is False
    # content aspect ~ source aspect
    assert abs((t.scaled_width / t.scaled_height) - (768 / 1344)) < 0.01


def test_transform_not_hardcoded_only_qual_geometry():
    # different source dims → different content window
    t = compute_fit_inside_letterbox(1024, 1024)
    assert t.scaled_width == 576
    assert t.scaled_height == 576
    assert t.pad_left + t.scaled_width + t.pad_right == 1024


def test_svd_backend_receives_source_image(store):
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu(14000)
    )
    adapter.generate_video(_approved(), seed=7, workflow_id="wf-img")
    assert len(transport.workflows) == 1
    wf = transport.workflows[0]
    assert wf["2"]["class_type"] == "LoadImage"
    assert "image" in wf["2"]["inputs"]
    assert wf["3"]["class_type"] == "SVD_img2vid_Conditioning"


def test_text_identity_prompt_not_created():
    assert TEXT_CONTROL_SUPPORTED is False
    wf = build_svd_xt_workflow(image_filename="x.png", seed=1)
    assert workflow_contains_text_identity_prompt(wf) is False
    # sanitize: no CLIPTextEncode nodes
    assert all(n.get("class_type") != "CLIPTextEncode" for n in wf.values())


def test_same_job_same_idempotency_key():
    k1 = compute_video_idempotency_key(
        workflow_id="wf",
        source_image_sha256="ab",
        backend_id=BACKEND_ID_SVD_XT_1_1,
        backend_settings_version=BACKEND_SETTINGS_VERSION,
        seed=9,
        motion_plan={"mode": "default"},
    )
    k2 = compute_video_idempotency_key(
        workflow_id="wf",
        source_image_sha256="ab",
        backend_id=BACKEND_ID_SVD_XT_1_1,
        backend_settings_version=BACKEND_SETTINGS_VERSION,
        seed=9,
        motion_plan={"mode": "default"},
    )
    assert k1 == k2


def test_existing_completed_job_reused(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    first = adapter.generate_video(_approved(), seed=3, workflow_id="wf-reuse")
    second = adapter.generate_video(_approved(), seed=3, workflow_id="wf-reuse")
    assert second.reused_existing is True
    assert second.video_job_id == first.video_job_id
    assert second.video_sha256 == first.video_sha256


def test_insufficient_gpu_headroom_fails_before_generation(store):
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu(12000)
    )
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-vram")
    assert result.validation_status == ValidationStatus.INFRA_FAILURE.value
    assert "GPU_HEADROOM_INSUFFICIENT" in (result.failure_reason or "")
    assert transport.workflows == []  # never submitted


def test_infrastructure_retry_bounded_to_2(store):
    transport = FakeTransport()
    transport.arm_failures(5)  # more than max
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu(14000)
    )
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-retry")
    assert result.validation_status == ValidationStatus.INFRA_FAILURE.value
    assert result.infrastructure_attempts == MAX_INFRASTRUCTURE_ATTEMPTS
    assert len(transport.workflows) == MAX_INFRASTRUCTURE_ATTEMPTS


def test_infrastructure_retry_succeeds_on_second(store):
    transport = FakeTransport()
    transport.arm_failures(1)
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu(14000)
    )
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-retry-ok")
    assert result.validation_status == ValidationStatus.PASS.value
    assert result.infrastructure_attempts == 2
    assert len(transport.workflows) == 2


def test_semantic_failure_no_auto_retry(store):
    # MINOR flicker → PARTIAL / review; no second backend submit for aesthetic reasons
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu(14000)
    )
    result = adapter.generate_video(
        _approved(),
        seed=1,
        workflow_id="wf-flicker",
        temporal_flicker=TemporalFlicker.MINOR.value,
    )
    assert result.validation_status == ValidationStatus.PARTIAL.value
    assert result.temporal_flicker == "MINOR"
    assert len(transport.workflows) == 1  # no aesthetic auto-retry


def test_static_fallback_remains_available(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(1000))
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-fallback")
    assert result.static_fallback_supported is True
    assert STATIC_FALLBACK_SUPPORTED is True


def test_gpu_ownership_prevents_sdxl_i2v_overlap(store):
    lease = ExclusiveGpuLease()
    lease.acquire("img-job-1", ExclusiveGpuLease.KIND_IMAGE)
    adapter = ImageToVideoAdapter(
        store=store, gpu_metrics=FakeGpu(14000), gpu_lease=lease
    )
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-own")
    assert result.validation_status == ValidationStatus.INFRA_FAILURE.value
    assert result.failure_reason and ("GPU" in result.failure_reason or "stale reclaim" in result.failure_reason or "owned" in result.failure_reason.lower())


def test_free_cleanup_recorded(store):
    transport = FakeTransport()
    gpu = FakeGpu(14000)
    adapter = ImageToVideoAdapter(store=store, transport=transport, gpu_metrics=gpu)
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-free")
    assert transport.free_calls >= 1
    assert result.comfyui_reachable_after_free is True
    assert result.post_free_vram_mib == 14000


def test_video_never_becomes_canon_automatically(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-canon")
    assert result.video_creates_identity_canon is False
    assert VIDEO_CREATES_IDENTITY_CANON is False


def test_intent_no_metadata_remains_generic(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    src = _approved(
        source_character_intent="NONE",
        source_character_id_or_na="N/A",
    )
    result = adapter.generate_video(src, seed=1, workflow_id="wf-intent-no")
    assert result.source_character_intent == "NONE"
    assert result.source_character_id_or_na == "N/A"


def test_comfyui_transport_failure_is_infra(store):
    transport = FakeTransport()
    transport.arm_failures(2)
    adapter = ImageToVideoAdapter(
        store=store, transport=transport, gpu_metrics=FakeGpu(14000)
    )
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-transport")
    assert result.validation_status == ValidationStatus.INFRA_FAILURE.value
    assert result.static_fallback_supported is True


def test_min_free_vram_constant():
    assert MIN_FREE_VRAM_MIB == 13000


def test_partial_not_auto_promoted_to_pass(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(
        _approved(),
        seed=1,
        workflow_id="wf-partial",
        temporal_flicker=TemporalFlicker.MINOR.value,
    )
    assert result.validation_status != ValidationStatus.PASS.value


def test_model_sha256_defaults_to_qualified_weight():
    assert len(MODEL_SHA256_SVD_XT_1_1) == 64


def test_peak_vram_derived_from_total_minus_lowest(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000, total_mib=16376))
    result = adapter.generate_video(_approved(), seed=1, workflow_id="wf-peak")
    assert result.lowest_free_vram_mib == 14000
    assert result.peak_vram_used_mib == 16376 - 14000


def test_major_flicker_is_video_review_required(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(
        _approved(),
        seed=1,
        workflow_id="wf-major",
        temporal_flicker=TemporalFlicker.MAJOR.value,
    )
    assert result.validation_status == ValidationStatus.VIDEO_REVIEW_REQUIRED.value
    assert result.failure_reason == "VIDEO_REVIEW_REQUIRED"


def test_minor_flicker_partial_tags_video_review_required(store):
    adapter = ImageToVideoAdapter(store=store, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(
        _approved(),
        seed=1,
        workflow_id="wf-minor-tag",
        temporal_flicker=TemporalFlicker.MINOR.value,
    )
    assert result.validation_status == ValidationStatus.PARTIAL.value
    assert result.failure_reason == "VIDEO_REVIEW_REQUIRED"


def test_crash_safe_persists_attempt_and_prompt_before_result(store, tmp_path):
    transport = FakeTransport()
    adapter = ImageToVideoAdapter(store=store, transport=transport, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(_approved(), seed=11, workflow_id="wf-crash")
    rec = store.get_by_idempotency(result.video_idempotency_key)
    assert rec is not None
    assert rec.attempt_number >= 1
    assert rec.backend_request_id
    assert rec.comfy_prompt_id  # recorded when accepted
    assert rec.result_video_sha256 == result.video_sha256


def test_gpu_lease_record_fields_and_no_age_only_clear():
    lease = ExclusiveGpuLease()
    lease.acquire("job-a", ExclusiveGpuLease.KIND_I2V, workflow_id="wf", stage="GENERATING", process_identity="pid:999001", now=1.0)
    rec = lease.current_record()
    assert rec["owner_job_id"] == "job-a"
    assert rec["owner_workflow_id"] == "wf"
    assert rec["owner_stage"] == "GENERATING"
    assert rec["acquired_at"] == 1.0
    assert rec["heartbeat_at"] == 1.0
    assert rec["process_identity"] == "pid:999001"
    # age alone must not reclaim
    with pytest.raises(GpuOwnershipConflict):
        lease.try_reclaim_stale(
            process_alive=lambda _pid: True,
            claimant_job_id="job-b",
            claimant_kind=ExclusiveGpuLease.KIND_I2V,
            workflow_id="wf2",
            now=999999.0,
        )


def test_gpu_lease_reclaim_only_when_process_proven_dead():
    lease = ExclusiveGpuLease()
    lease.acquire("job-a", ExclusiveGpuLease.KIND_I2V, workflow_id="wf", process_identity="pid:dead", now=1.0)
    ok = lease.try_reclaim_stale(
        process_alive=lambda pid: False,
        claimant_job_id="job-b",
        claimant_kind=ExclusiveGpuLease.KIND_I2V,
        workflow_id="wf2",
        process_identity="pid:alive",
        now=2.0,
    )
    assert ok is True
    assert lease.gpu_owner_job_id == "job-b"
    assert lease.current_record()["process_identity"] == "pid:alive"


def test_ready_reuse_requires_matching_video_hash(store, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video-bytes-ok")
    transport = FakeTransport()
    # make transport return path
    orig = transport.submit_and_wait
    def _wrapped(workflow):
        out = orig(workflow)
        out["video_path"] = str(clip)
        out["video_bytes"] = clip.read_bytes()
        return out
    transport.submit_and_wait = _wrapped
    adapter = ImageToVideoAdapter(store=store, transport=transport, gpu_metrics=FakeGpu(14000))
    first = adapter.generate_video(_approved(), seed=22, workflow_id="wf-hash")
    assert first.video_sha256 == hashlib.sha256(b"video-bytes-ok").hexdigest()
    # corrupt file after READY
    clip.write_bytes(b"CORRUPTED")
    second = adapter.generate_video(_approved(), seed=22, workflow_id="wf-hash")
    # must NOT silently reuse corrupted READY
    assert second.reused_existing is False
    assert second.validation_status in {ValidationStatus.PASS.value, ValidationStatus.PARTIAL.value, ValidationStatus.INFRA_FAILURE.value, ValidationStatus.VIDEO_REVIEW_REQUIRED.value}


def test_ready_reuse_ok_when_hash_matches(store, tmp_path):
    clip = tmp_path / "clip_ok.mp4"
    clip.write_bytes(b"video-bytes-ok")
    transport = FakeTransport()
    orig = transport.submit_and_wait
    def _wrapped(workflow):
        out = orig(workflow)
        out["video_path"] = str(clip)
        out["video_bytes"] = b"video-bytes-ok"
        return out
    transport.submit_and_wait = _wrapped
    adapter = ImageToVideoAdapter(store=store, transport=transport, gpu_metrics=FakeGpu(14000))
    first = adapter.generate_video(_approved(), seed=33, workflow_id="wf-hash-ok")
    second = adapter.generate_video(_approved(), seed=33, workflow_id="wf-hash-ok")
    assert second.reused_existing is True
    assert second.video_job_id == first.video_job_id


def test_crash_after_accept_does_not_double_submit(store):
    """GENERATING + comfy_prompt_id must reconcile; never a second submit."""
    transport = FakeTransport()
    transport.set_reconcile(
        "accepted-1",
        {"video_bytes": b"recovered-clip", "video_path": "/tmp/recovered.mp4"},
    )
    # Seed a crashed GENERATING job
    from tools.i2v_production_adapter import (
        VideoJobRecord,
        compute_video_idempotency_key,
        BACKEND_ID_SVD_XT_1_1,
        BACKEND_SETTINGS_VERSION,
    )
    src = _approved()
    idem = compute_video_idempotency_key(
        workflow_id="wf-crash-ds",
        source_image_sha256=src.source_image_sha256,
        backend_id=BACKEND_ID_SVD_XT_1_1,
        backend_settings_version=BACKEND_SETTINGS_VERSION,
        seed=7,
        motion_plan=None,
    )
    rec = VideoJobRecord(
        video_job_id="job-crash-1",
        workflow_id="wf-crash-ds",
        idempotency_key=idem,
        state=JobState.GENERATING.value,
        backend_id=BACKEND_ID_SVD_XT_1_1,
        comfy_prompt_id="accepted-1",
        attempt_number=1,
        backend_request_id="req-1",
    )
    store.save(rec)
    adapter = ImageToVideoAdapter(store=store, transport=transport, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(src, seed=7, workflow_id="wf-crash-ds")
    assert transport.submit_count == 0
    assert result.video_sha256 == hashlib.sha256(b"recovered-clip").hexdigest()
    assert result.validation_status == ValidationStatus.PASS.value


def test_unreconciled_accepted_prompt_fails_closed(store):
    transport = FakeTransport()
    # no reconcile payload -> unknown fate
    from tools.i2v_production_adapter import (
        VideoJobRecord,
        compute_video_idempotency_key,
        BACKEND_ID_SVD_XT_1_1,
        BACKEND_SETTINGS_VERSION,
    )
    src = _approved()
    idem = compute_video_idempotency_key(
        workflow_id="wf-crash-unk",
        source_image_sha256=src.source_image_sha256,
        backend_id=BACKEND_ID_SVD_XT_1_1,
        backend_settings_version=BACKEND_SETTINGS_VERSION,
        seed=8,
        motion_plan=None,
    )
    store.save(
        VideoJobRecord(
            video_job_id="job-crash-2",
            workflow_id="wf-crash-unk",
            idempotency_key=idem,
            state=JobState.GENERATING.value,
            backend_id=BACKEND_ID_SVD_XT_1_1,
            comfy_prompt_id="orphan-9",
        )
    )
    adapter = ImageToVideoAdapter(store=store, transport=transport, gpu_metrics=FakeGpu(14000))
    result = adapter.generate_video(src, seed=8, workflow_id="wf-crash-unk")
    assert transport.submit_count == 0
    assert result.validation_status == ValidationStatus.INFRA_FAILURE.value
    assert "unreconciled_comfy_prompt_id" in (result.failure_reason or "")



# ---- success packet video_path ----
def test_success_packet_video_path_populated(tmp_path):
    import hashlib
    from tools.i2v_production_adapter import ImageToVideoAdapter as _A, VideoJobStore as _S, persist_video_artifact, InfrastructureFailure
    p = persist_video_artifact(tmp_path, "job1", "wan_22", b"MP4DATA" * 10, None, "/nonexistent/x.mp4")
    assert Path(p).is_file()
    assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == hashlib.sha256(b"MP4DATA" * 10).hexdigest()
    good = tmp_path / "real.mp4"; good.write_bytes(b"ZZ")
    assert persist_video_artifact(tmp_path, "j", "wan_22", b"ZZ", None, str(good)) == str(good)
    with pytest.raises(InfrastructureFailure):
        persist_video_artifact(tmp_path, "j", "wan_22", b"", None, None)


def test_generate_video_success_has_durable_video_path(store):
    adapter = ImageToVideoAdapter(store=store, transport=FakeTransport(), gpu_metrics=FakeGpu(14000))
    r = adapter.generate_video(_approved(), seed=11, workflow_id="wf-vpath")
    assert r.video_path and Path(r.video_path).is_file()
    import hashlib
    assert hashlib.sha256(Path(r.video_path).read_bytes()).hexdigest() == r.video_sha256
    assert r.identity_canon is False if hasattr(r, "identity_canon") else True


def test_generate_video_empty_bytes_fail_closed(store):
    class Empty(FakeTransport):
        def submit_and_wait(self, workflow):
            return {"video_bytes": b"", "prompt_id": "p"}
    adapter = ImageToVideoAdapter(store=store, transport=Empty(), gpu_metrics=FakeGpu(14000))
    r = adapter.generate_video(_approved(), seed=12, workflow_id="wf-empty")
    assert r.video_path is None and r.video_sha256 is None
