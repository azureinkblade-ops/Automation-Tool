"""Wan frame integrity + presentation hardening (CPU only; ComfyUI is never contacted, no GPU).

Evidence (Research png-app-20261121-174605, 2026-11-21):
  * runs 2/3: raw + presented mp4 had 72 frames, one pts hole (idx 61 / 60). The PNGs were fine: ffmpeg's PNG
    decoder hit "inflate returned error -3" on a good file, dropped it, and still exited 0. Our check only counted
    the PNG files, and the final gate only wanted >0 frames and >=3 s (72 frames with a hole still last 3.04 s).
  * run 1: the 9x16 presentation ffmpeg crashed (0xC0000005, Windows event log) at frame 48; only 500 chars of
    stderr were kept and no exit code. Reproduced on CPU: multithreaded ffmpeg crashed/dropped frames
    intermittently, single-threaded runs were clean.
Fixes covered here: PNG verify+load at the expected size with one re-fetch; -xerror/-err_detect explode and
-threads 1 on every ffmpeg; ffprobe -count_frames on the raw and presented mp4 (exactly 73, contiguous pts, else a
Wan failure); last 2000 chars of stderr + exit code; one presentation-only retry from the saved raw clip, inside the
step deadline and the cancel flag, recorded as presentation_retry.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import chapter_video_wiring as cvw
from tools import comfy_http_i2v_transport as T
from tools import i2v_presentation_adapter as pa
from tools import i2v_production_adapter as A
from tools import media_pipeline_i2v_wiring as wiring
from tools import media_pipeline_integration as mpi
from tools import video_frame_probe as vfp
from tools.media_validity import MediaProbeInfo, MediaValidityResult
from tests.test_chapter_video_wiring import CFG, _still
from tests.test_wan22_png_frames_encode import FakeComfy, FakeRun, PREFIX, W, H, _items, _png, _transport, _wan_wf


@pytest.fixture(autouse=True)
def _reset_lease():
    A.reset_default_gpu_lease()
    yield
    A.reset_default_gpu_lease()


# =========================================================================== transport: PNG integrity

BAD = f"{PREFIX}_00040_.png"


def test_truncated_png_is_refetched_once_then_used(tmp_path):
    served = {}

    def frame(fn):
        served[fn] = served.get(fn, 0) + 1
        good = _png(fn)
        return good[: len(good) // 2] if fn == BAD and served[fn] == 1 else good  # first fetch cut short

    fake, run = FakeComfy(_items(range(1, 74)), frame_bytes=frame), FakeRun()
    out = _transport(fake, run).submit_and_wait(_wan_wf())
    assert served[BAD] == 2 and len(fake.views) == 74
    assert out["comfy_output"]["png_refetched"] == [BAD]
    assert dict(run.frames)["00040.png"] == _png(BAD)  # the re-fetched, complete frame was encoded


def test_png_still_corrupt_after_refetch_is_a_wan_failure_and_never_encodes():
    fake = FakeComfy(_items(range(1, 74)), frame_bytes=lambda fn: _png(fn)[:-30] if fn == BAD else _png(fn))
    run = FakeRun()
    with pytest.raises(T.ComfyJobFailed, match="unusable after re-fetch: PNG does not decode") as e:
        _transport(fake, run).submit_and_wait(_wan_wf())
    assert isinstance(e.value, A.InfrastructureFailure) and run.argv is None
    assert fake.views.count(BAD) == 2


def test_png_at_the_wrong_size_is_rejected():
    fake = FakeComfy(_items(range(1, 74)), frame_bytes=lambda fn: _png(fn, (W, H + 2)) if fn == BAD else _png(fn))
    with pytest.raises(T.ComfyJobFailed, match=f"PNG is {W}x{H + 2}, expected {W}x{H}"):
        _transport(fake, FakeRun()).submit_and_wait(_wan_wf())


def test_view_fetch_error_is_retried_once():
    fake, failed = FakeComfy(_items(range(1, 74))), []

    def flaky(req, timeout=None):
        if BAD in req.full_url and not failed:
            failed.append(1)
            raise OSError("connection reset")
        return fake(req, timeout)

    out = _transport(flaky, FakeRun()).submit_and_wait(_wan_wf())
    assert failed and out["comfy_output"]["png_refetched"] == [BAD]


# =========================================================================== transport: encoded mp4 is re-probed

@pytest.mark.parametrize("probe,match", [
    (vfp.FrameProbe(path="o", frames=72, packets=72, missing_indices=[61]), "FRAME_COUNT_MISMATCH:probed=72,expected=73"),
    (vfp.FrameProbe(path="o", frames=73, packets=73, missing_indices=[60]), r"FRAME_PTS_GAP:missing_idx=\[60\]"),
    (vfp.FrameProbe(path="o", error="ffprobe_unavailable"), "FRAME_PROBE_FAILED:ffprobe_unavailable"),
])
def test_encoded_mp4_with_wrong_frames_is_a_wan_failure(probe, match):
    run = FakeRun()
    with pytest.raises(T.ComfyJobFailed, match=match) as e:
        _transport(FakeComfy(_items(range(1, 74))), run, frame_probe=lambda p: probe).submit_and_wait(_wan_wf())
    assert isinstance(e.value, A.InfrastructureFailure)
    assert run.argv is not None and not os.path.exists(run.frames_dir)  # encoded, rejected, temp cleaned


def test_encoded_mismatch_goes_through_the_adapter_failure_path(tmp_path):
    from tests.test_wan22_png_frames_encode import _FakeGpu, _approved_png
    fake = FakeComfy(_items(range(1, 74)))
    tr = _transport(fake, FakeRun(), frame_probe=lambda p: vfp.FrameProbe(path=p, frames=72, packets=72, missing_indices=[61]))
    ad = A.ImageToVideoAdapter(store=A.VideoJobStore(tmp_path / "s"), transport=tr, gpu_metrics=_FakeGpu())
    # the adapter builds its own native-size graph: serve frames at that size
    fake.frame_bytes = lambda fn: _png(fn, (A.WAN22_NATIVE_WIDTH, A.WAN22_NATIVE_HEIGHT))
    res = ad.generate_video(_approved_png(), seed=5, backend_id="wan_22", workflow_id="wf-72", motion_plan={"length": 73})
    assert res.validation_status == A.ValidationStatus.INFRA_FAILURE.value
    assert "FRAME_COUNT_MISMATCH" in (res.failure_reason or "")


def test_encode_argv_stops_on_decode_error_single_threaded_every_frame():
    argv = T.build_frames_encode_argv("ff", "D", 24, "o.mp4", frames=73)
    i = argv.index("-i")
    assert argv[argv.index("-xerror")] and argv[argv.index("-err_detect") + 1] == "explode" and argv.index("-xerror") < i
    assert argv[argv.index("-start_number") + 1] == "1" and argv.index("-start_number") < i
    assert argv[argv.index("-frames:v") + 1] == "73" and argv[argv.index("-fps_mode") + 1] == "passthrough"
    assert [argv[k + 1] for k, a in enumerate(argv) if a == "-threads"] == ["1", "1"]  # decoder and encoder


def test_ffmpeg_failure_keeps_the_last_2000_chars_and_hex_exit_code():
    class LoggingRun(FakeRun):
        def __call__(self, argv, **kwargs):
            kwargs["stdout"].write(b"BANNER_START " + b"x" * 5000 + b" inflate returned error -3 ERROR_AT_END")
            super().__call__(argv, **kwargs)
            return subprocess.CompletedProcess(argv, 3221225477)  # 0xC0000005

    with pytest.raises(T.ComfyJobFailed) as e:
        _transport(FakeComfy(_items(range(1, 74))), LoggingRun()).submit_and_wait(_wan_wf())
    msg = str(e.value)
    assert "ERROR_AT_END" in msg and "BANNER_START" not in msg and "0xC0000005" in msg
    assert vfp.STDERR_TAIL_CHARS == 2000 and len(msg) < 2300


@pytest.mark.skipif(not (T.resolve_ffmpeg() and vfp.resolve_ffprobe()), reason="needs ffmpeg + ffprobe")
def test_real_ffmpeg_73_distinct_pngs_encode_to_exactly_73_contiguous_frames(tmp_path):
    from PIL import Image

    def frame(fn):
        i = int(fn.rsplit("_", 2)[-2])
        b = io.BytesIO()
        Image.new("RGB", (W, H), ((i * 37) % 256, (i * 11) % 256, 200)).save(b, format="PNG")
        return b.getvalue()

    tr = T.select_i2v_transport("wan_22", opener=FakeComfy(_items(range(1, 74)), frame_bytes=frame), sleep=lambda s: None)
    out = tr.submit_and_wait(_wan_wf())  # real ffmpeg encode + real ffprobe check inside the transport
    mp4 = tmp_path / "raw.mp4"
    mp4.write_bytes(out["video_bytes"])
    probe = vfp.probe_frames(mp4)
    assert (probe.frames, probe.packets, probe.missing_indices, probe.contiguous) == (73, 73, [], True)
    assert vfp.frame_check_failure(probe, 73) is None and vfp.frame_check_failure(probe, 72) is not None


@pytest.mark.skipif(not (T.resolve_ffmpeg() and vfp.resolve_ffprobe()), reason="needs ffmpeg + ffprobe")
def test_real_probe_counts_a_short_sequence(tmp_path):
    """A frame sequence with frame 62 missing never comes out as 73 frames: the probe count rejects it."""
    ff = T.resolve_ffmpeg()
    src = tmp_path / "f"
    src.mkdir()
    from PIL import Image
    for i in range(1, 74):
        if i != 62:
            Image.new("RGB", (W, H), (i, 0, 0)).save(src / f"{i:05d}.png")
    out = tmp_path / "short.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-framerate", "24", "-start_number", "1", "-i", str(src / "%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=False, capture_output=True, timeout=120)
    probe = vfp.probe_frames(out)
    assert probe.frames == 61 and vfp.frame_check_failure(probe, 73).startswith("FRAME_COUNT_MISMATCH:probed=61")


# =========================================================================== presentation ffmpeg runner

def _clip(tmp_path, name="raw.mp4", frames=73, fps=24):
    p = tmp_path / name
    p.write_bytes(b"raw-mp4")
    return pa.RawI2VClipRef(video_path=str(p), video_sha256=hashlib.sha256(b"raw-mp4").hexdigest(),
                            source_image_sha256="s" * 64, width=720, height=1280, frame_count=frames, fps=fps)


def test_presentation_ffmpeg_is_safe_bounded_and_keeps_the_stderr_tail(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 3221225477, b"", b"HEAD " + b"y" * 4000 + b" frame=   48 CRASH_TAIL")

    monkeypatch.setattr(pa, "shutil", SimpleNamespace(which=lambda n: "ffmpeg-x"))
    monkeypatch.setattr(pa.subprocess, "run", fake_run)
    clip = _clip(tmp_path)
    tf = pa.compute_fit_inside_letterbox_9x16(source_width=720, source_height=1280, target_width=1080, target_height=1920)
    with pytest.raises(pa.PresentationError) as e:
        pa.default_ffmpeg_render(clip, tf, tmp_path / "o.mp4", timeout_s=42)
    msg = str(e.value)
    assert "CRASH_TAIL" in msg and "HEAD" not in msg and "0xC0000005" in msg and "frame=   48" in msg
    cmd, kw = seen["cmd"], seen["kw"]
    assert cmd.index("-xerror") < cmd.index("-i") and cmd[cmd.index("-err_detect") + 1] == "explode"
    assert [cmd[k + 1] for k, a in enumerate(cmd) if a == "-threads"] == ["1", "1"]
    assert kw["stdin"] is subprocess.DEVNULL and kw["timeout"] == 42 and kw.get("capture_output") is True


def test_presentation_ffmpeg_timeout_is_a_presentation_error(tmp_path, monkeypatch):
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"], stderr=b"tail-of-log")

    monkeypatch.setattr(pa, "shutil", SimpleNamespace(which=lambda n: "ffmpeg-x"))
    monkeypatch.setattr(pa.subprocess, "run", fake_run)
    tf = pa.compute_fit_inside_letterbox_9x16(source_width=720, source_height=1280, target_width=1080, target_height=1920)
    with pytest.raises(pa.PresentationError, match="timed out after 300s: tail-of-log"):
        pa.default_ffmpeg_render(_clip(tmp_path), tf, tmp_path / "o.mp4", timeout_s=10_000)  # capped at 300 s


# =========================================================================== MediaPipeline presentation-only retry

class FakeI2V:
    def __init__(self, raw: Path):
        self.raw, self.calls = raw, 0

    def generate_video(self, still, *, seed, workflow_id):
        self.calls += 1
        return {"validation_status": "PASS", "video_path": str(self.raw),
                "video_sha256": hashlib.sha256(self.raw.read_bytes()).hexdigest(), "video_job_id": "vj"}


class FakePresentation:
    def __init__(self, tmp_path, outcomes):
        self.tmp, self.outcomes, self.calls = tmp_path, list(outcomes), 0

    def present_video(self, raw, sha, src_sha, *, workflow_id):
        self.calls += 1
        if self.outcomes.pop(0) == "fail":
            return {"validation_status": "INFRA_FAILURE", "failure_reason": "ffmpeg failed (exit 3221225477 / 0xC0000005): frame=48"}
        out = self.tmp / f"p{self.calls}.mp4"
        out.write_bytes(b"p" * 30000)
        return {"validation_status": "PASS", "presented_video_path": str(out),
                "presented_video_sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "presentation_job_id": "pj"}


def _ok_validator(path, **kw):
    return MediaValidityResult(ok=True, probe=MediaProbeInfo(exists=True, duration=73 / 24, frame_count=73,
                                                             width=1080, height=1920, decodable=True))


def _pipeline(tmp_path, outcomes, retries=1, allowed=None):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"raw")
    i2v, pres = FakeI2V(raw), FakePresentation(tmp_path, outcomes)
    pipe = mpi.MediaPipeline(store=mpi.MediaRecordStore(tmp_path / "rec"), i2v=i2v, presentation=pres,
                             media_validator=_ok_validator, presentation_retries=retries,
                             presentation_retry_allowed=allowed)
    return pipe, i2v, pres


def _still_ref(tmp_path):
    p = _still(tmp_path)
    return mpi.ApprovedStillRef(image_path=str(p), source_image_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                image_source_approved=True, source_character_intent="INTENT_NO",
                                source_width=768, source_height=1344)


def test_presentation_retry_recovers_without_a_new_render(tmp_path):
    pipe, i2v, pres = _pipeline(tmp_path, ["fail", "ok"])
    res = pipe.produce_social_media(_still_ref(tmp_path), workflow_id="wf", seed=1)
    assert res.outcome == "SOCIAL_READY" and res.presentation_retry == "recovered"
    assert pres.calls == 2 and i2v.calls == 1  # re-presented from the saved raw clip; Wan not re-rendered


def test_presentation_retry_failing_again_is_a_hold_with_the_reason(tmp_path):
    pipe, i2v, pres = _pipeline(tmp_path, ["fail", "fail"])
    res = pipe.produce_social_media(_still_ref(tmp_path), workflow_id="wf", seed=1)
    assert res.outcome == "MEDIA_HOLD" and res.presentation_retry == "failed"
    assert "presentation_retry=failed" in res.failure_reason and "0xC0000005" in res.failure_reason
    assert pres.calls == 2 and i2v.calls == 1


def test_presentation_retry_skipped_when_not_allowed(tmp_path):
    pipe, i2v, pres = _pipeline(tmp_path, ["fail", "ok"], allowed=lambda: "cancelled")
    res = pipe.produce_social_media(_still_ref(tmp_path), workflow_id="wf", seed=1)
    assert res.outcome == "MEDIA_HOLD" and res.presentation_retry == "skipped:cancelled" and pres.calls == 1


def test_library_default_has_no_presentation_retry(tmp_path):
    pipe, i2v, pres = _pipeline(tmp_path, ["fail", "ok"], retries=0)
    res = pipe.produce_social_media(_still_ref(tmp_path), workflow_id="wf", seed=1)
    assert res.outcome == "MEDIA_HOLD" and res.presentation_retry == "" and pres.calls == 1


# =========================================================================== wiring: PresentationGuard

def _probe_map(raw_frames=73, pres_frames=73, pres_missing=()):
    def probe(path, **kw):
        if Path(path).parent.name == "presented" or Path(path).name in ("o.mp4",) or Path(path).name.endswith("_9x16.mp4"):
            return vfp.FrameProbe(path=str(path), frames=pres_frames, packets=pres_frames, missing_indices=list(pres_missing))
        return vfp.FrameProbe(path=str(path), frames=raw_frames, packets=raw_frames)
    return probe


def _guard(cancelled=False, left=1000.0, base=None):
    calls = []

    def render(clip, tf, out, *, timeout_s=None):
        calls.append(timeout_s)
        Path(out).write_bytes(b"presented")
        return b"presented"

    g = cvw.PresentationGuard(73, cancelled=lambda: cancelled, remaining=lambda: left, base_render=base or render)
    return g, calls


def test_guard_cancelled_never_starts_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(vfp, "probe_frames", _probe_map())
    g, calls = _guard(cancelled=True)
    with pytest.raises(pa.PresentationError, match="CLIP_STEP_CANCELLED:presentation_not_started:cancelled"):
        g(_clip(tmp_path), None, tmp_path / "o.mp4")
    assert calls == [] and g.retry_allowed() != True  # noqa: E712


def test_guard_out_of_time_never_starts_ffmpeg_and_bounds_by_time_left(tmp_path, monkeypatch):
    monkeypatch.setattr(vfp, "probe_frames", _probe_map())
    g, calls = _guard(left=cvw.PRESENTATION_MIN_BUDGET_S - 1)
    with pytest.raises(pa.PresentationError, match="CLIP_STEP_TIMEOUT:presentation_not_started:no_time_left"):
        g(_clip(tmp_path), None, tmp_path / "o.mp4")
    assert calls == []
    g2, calls2 = _guard(left=95.0)
    g2(_clip(tmp_path), None, tmp_path / "o.mp4")
    assert calls2 == [95.0] and g2.probes["raw"]["frames"] == 73 and g2.probes["presented"]["frames"] == 73


def test_guard_raw_mismatch_rejects_and_disallows_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(vfp, "probe_frames", _probe_map(raw_frames=72))
    g, calls = _guard()
    with pytest.raises(pa.PresentationError, match="RAW_CLIP_REJECTED:FRAME_COUNT_MISMATCH:probed=72,expected=73"):
        g(_clip(tmp_path), None, tmp_path / "o.mp4")
    assert calls == [] and g.raw_ok is False and g.retry_allowed() == "raw_clip_not_verified"


def test_guard_presented_mismatch_rejects_but_allows_one_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(vfp, "probe_frames", _probe_map(pres_frames=72, pres_missing=[61]))
    g, calls = _guard()
    with pytest.raises(pa.PresentationError, match="PRESENTED_CLIP_REJECTED:FRAME_COUNT_MISMATCH:probed=72"):
        g(_clip(tmp_path), None, tmp_path / "o.mp4")
    assert len(calls) == 1 and g.raw_ok is True and g.retry_allowed() is True


# =========================================================================== wiring end-to-end (real pipeline path)

class _Renders:
    """Stands in for pa.default_ffmpeg_render. ``plan`` per backend: list of 'fail' | 'ok' | callables."""

    def __init__(self, plan):
        self.plan, self.calls = {k: list(v) for k, v in plan.items()}, []

    def __call__(self, clip, tf, out_path, *, timeout_s=None):
        backend = "wan_22" if "wan_22" in str(out_path) else "svd_xt_1_1"
        self.calls.append((backend, timeout_s))
        step = self.plan[backend].pop(0) if self.plan[backend] else "ok"
        if callable(step):
            step = step()
        if step == "fail":
            raise pa.PresentationError("ffmpeg failed (exit 3221225477 / 0xC0000005): frame=   48")
        Path(out_path).write_bytes(b"P" * 40000)
        return Path(out_path).read_bytes()


def _e2e(tmp_path, monkeypatch, renders, *, raw_frames=None, pres_frames=None, state=None):
    raw_frames = raw_frames or {"wan_22": 73, "svd_xt_1_1": 25}
    pres_frames = pres_frames or {"wan_22": 73, "svd_xt_1_1": 25}
    i2v_calls = []

    def builder(cfg, backend, store_root, *, render=None, **kw):
        root = Path(store_root) / backend
        root.mkdir(parents=True, exist_ok=True)
        raw = root / f"raw_{backend}.mp4"
        raw.write_bytes(backend.encode() * 100)

        class I2V:
            def generate_video(self, still, *, seed, workflow_id):
                i2v_calls.append(backend)
                return {"validation_status": "PASS", "video_path": str(raw),
                        "video_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "video_job_id": f"vj-{backend}"}

        adapter = pa.I2VPresentationAdapter(store=pa.PresentationJobStore(root / "presentation_jobs"),
                                            render=render, output_dir=root / "presented")
        return mpi.MediaPipeline(store=mpi.MediaRecordStore(root / "media_records"), i2v=I2V(),
                                 presentation=wiring.PresentationAdapterPort(adapter=adapter),
                                 media_validator=_ok_validator, video_required=True)

    def probe(path, **kw):
        b = "wan_22" if "wan_22" in str(path) else "svd_xt_1_1"
        n = (pres_frames if Path(path).parent.name == "presented" else raw_frames)[b]
        return vfp.FrameProbe(path=str(path), frames=n, packets=n)

    def validator(path, **kw):
        b = "wan_22" if "wan_22" in str(path) else "svd_xt_1_1"
        return MediaValidityResult(ok=True, probe=MediaProbeInfo(exists=True, duration=pres_frames[b] / (24 if b == "wan_22" else 6),
                                                                 frame_count=pres_frames[b], width=1080, height=1920, decodable=True))

    monkeypatch.setattr(cvw, "build_backend_pipeline", builder)
    monkeypatch.setattr(pa, "default_ffmpeg_render", renders)
    monkeypatch.setattr(vfp, "probe_frames", probe)
    monkeypatch.setattr(cvw, "validate_presented_social_video", validator)
    res = cvw._produce_chapter_clip_inner(_still(tmp_path), workflow_id="chapter-clip:e2e", store_root=tmp_path / "store",
                                          still_approved=True, cfg=CFG, skip_comfy_guard=True, _state=state or {})
    return res, i2v_calls


def test_e2e_presentation_crash_is_retried_once_from_the_raw_clip_and_stays_wan(tmp_path, monkeypatch):
    renders = _Renders({"wan_22": ["fail", "ok"]})
    res, i2v_calls = _e2e(tmp_path, monkeypatch, renders)
    assert res.outcome == cvw.SOCIAL_READY and res.backend_used == "wan_22" and not res.fallback_used
    assert res.presentation_retry == "recovered" and res.clip_metadata["presentation_retry"] == "recovered"
    assert i2v_calls == ["wan_22"] and [b for b, _ in renders.calls] == ["wan_22", "wan_22"]  # no Wan re-render
    m = res.clip_metadata
    assert m["raw_frame_count"] == 73 and m["raw_frame_count_source"] == "ffprobe" and m["raw_pts_missing"] == []
    assert m["output_frame_count"] == 73 and m["output_pts_missing"] == []


def test_e2e_retry_failing_again_falls_back_to_svd(tmp_path, monkeypatch):
    renders = _Renders({"wan_22": ["fail", "fail"], "svd_xt_1_1": ["ok"]})
    res, i2v_calls = _e2e(tmp_path, monkeypatch, renders)
    assert res.backend_used == "svd_xt_1_1" and res.social_hold and res.hold_reason == cvw.SVD_FALLBACK_SOCIAL_HOLD
    wan = res.attempts[0]
    assert wan["backend"] == "wan_22" and wan["presentation_retry"] == "failed" and "0xC0000005" in wan["reason"]
    assert i2v_calls == ["wan_22", "svd_xt_1_1"]
    assert res.clip_metadata["raw_frame_count"] == 25 and res.clip_metadata["raw_frame_count_source"] == "ffprobe"


def test_e2e_cancel_during_presentation_skips_the_retry_and_everything_after(tmp_path, monkeypatch):
    cancel = threading.Event()

    def crash_and_cancel():
        cancel.set()  # the step deadline fires while the first presentation runs
        return "fail"

    renders = _Renders({"wan_22": [crash_and_cancel, "ok"], "svd_xt_1_1": ["ok"]})
    res, i2v_calls = _e2e(tmp_path, monkeypatch, renders, state={"cancel": cancel})
    assert res.outcome == "MEDIA_HOLD" and not res.clip_produced
    assert res.attempts[0]["presentation_retry"] == "skipped:cancelled"
    assert [b for b, _ in renders.calls] == ["wan_22"] and i2v_calls == ["wan_22"]  # no retry, no SVD
    assert any(a.get("outcome") == cvw.CLIP_STEP_CANCELLED for a in res.attempts)


def test_e2e_retry_counts_against_the_step_deadline(tmp_path, monkeypatch):
    def slow_crash():
        time.sleep(1.2)  # the first presentation eats the budget: under PRESENTATION_MIN_BUDGET_S left
        return "fail"

    renders = _Renders({"wan_22": [slow_crash, "ok"], "svd_xt_1_1": ["ok"]})
    deadline = time.monotonic() + cvw.PRESENTATION_MIN_BUDGET_S + 1.0
    res, _ = _e2e(tmp_path, monkeypatch, renders, state={"deadline": deadline})
    assert res.attempts[0]["presentation_retry"] == "skipped:no_time_left"
    assert [b for b, _ in renders.calls][:1] == ["wan_22"] and renders.calls[0][1] <= cvw.PRESENTATION_MIN_BUDGET_S + 1.0
    assert ("wan_22", None) not in renders.calls  # every presentation ffmpeg got a bounded timeout


def test_e2e_raw_wan_mismatch_fails_over_without_presentation_retry(tmp_path, monkeypatch):
    renders = _Renders({"svd_xt_1_1": ["ok"]})
    res, _ = _e2e(tmp_path, monkeypatch, renders, raw_frames={"wan_22": 72, "svd_xt_1_1": 25})
    wan = res.attempts[0]
    assert "RAW_CLIP_REJECTED:FRAME_COUNT_MISMATCH:probed=72,expected=73" in wan["reason"]
    assert wan["presentation_retry"] == "skipped:raw_clip_not_verified"
    assert [b for b, _ in renders.calls] == ["svd_xt_1_1"] and res.backend_used == "svd_xt_1_1"


def test_e2e_presented_72_frames_is_a_wan_failure_and_fails_over(tmp_path, monkeypatch):
    renders = _Renders({"wan_22": ["ok", "ok"], "svd_xt_1_1": ["ok"]})
    res, _ = _e2e(tmp_path, monkeypatch, renders, pres_frames={"wan_22": 72, "svd_xt_1_1": 25})
    wan = res.attempts[0]
    assert "PRESENTED_CLIP_REJECTED:FRAME_COUNT_MISMATCH:probed=72,expected=73" in wan["reason"]
    assert wan["presentation_retry"] == "failed"
    assert res.backend_used == "svd_xt_1_1" and res.outcome == "MEDIA_HOLD" and res.outcome != cvw.SOCIAL_READY
