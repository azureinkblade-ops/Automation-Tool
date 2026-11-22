"""Wan 2.2 saves PNG frames; the transport encodes the mp4 locally with ffmpeg (CPU only, never contacts ComfyUI).

ComfyUI's own CreateVideo/SaveVideo step crashed ComfyUI while encoding (Research, 2026-11-21). The Wan graph now
ends in SaveImage fed by the tiled decode (node 8); ComfyHttpI2VTransport fetches every frame through /view in
frame-index order, checks the count, and runs ffmpeg locally. Short/missing frames or an ffmpeg failure are an
ordinary Wan failure (ComfyJobFailed -> InfrastructureFailure), so the normal retry / SVD-fallback path applies.
"""
from __future__ import annotations

import io
import json
import os
import random
import shutil
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from tools import comfy_http_i2v_transport as T
from tools import i2v_production_adapter as A
from tools import video_frame_probe as vfp
from tools.i2v_backend_registry import BACKEND_ID_WAN_22

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PREFIX = "i2v_wan22_job1_a1_abcdef0123"
ALL_MODELS = {
    "/models/diffusion_models": ["wan2.2_ti2v_5B_fp16.safetensors"],
    "/models/text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
    "/models/vae": ["wan2.2_vae.safetensors"],
}


@pytest.fixture(autouse=True)
def _reset_lease():
    A.reset_default_gpu_lease()
    yield
    A.reset_default_gpu_lease()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


W, H = 64, 112  # small frames keep the PNG decode checks fast; the graph's latent size says what to expect


def _wan_wf(length=73, prefix=PREFIX, width=W, height=H):
    return A.build_wan_22_ti2v_workflow(image_filename="src.png", seed=7, length=length, filename_prefix=prefix,
                                        width=width, height=height)


_PNG_CACHE = {}


def _png(fn="", size=(W, H)):
    """A real, fully decodable PNG (distinct per frame name)."""
    key = (fn, size)
    if key not in _PNG_CACHE:
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", size, (sum(fn.encode()) % 256, 40, 200)).save(b, format="PNG")
        _PNG_CACHE[key] = b.getvalue()
    return _PNG_CACHE[key]


def _items(counters, prefix=PREFIX):
    return [{"filename": f"{prefix}_{i:05d}_.png", "subfolder": "", "type": "output"} for i in counters]


class FakeComfy:
    """urllib opener stand-in: /prompt, /history, /view, /upload/image, model listings."""

    def __init__(self, items, *, node="60", extra_outputs=None, frame_bytes=None):
        outputs = {node: {"images": items}}
        outputs.update(extra_outputs or {})
        self.history = {"pid": {"status": {"completed": True, "status_str": "success"}, "outputs": outputs}}
        self.frame_bytes = frame_bytes or (lambda fn: _png(fn))
        self.calls, self.views, self.prompts = [], [], 0

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append((req.get_method(), url))
        if "/system_stats" in url:
            body = {}
        elif "/models/" in url:
            body = next(v for k, v in ALL_MODELS.items() if k in url)
        elif "/upload/image" in url:
            body = {"name": "i2v_src.png", "subfolder": "", "type": "input"}
        elif url.endswith("/prompt"):
            self.prompts += 1
            body = {"prompt_id": "pid", "node_errors": {}}
        elif "/history/pid" in url:
            body = self.history
        elif "/view?" in url:
            fn = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["filename"][0]
            self.views.append(fn)
            return _Resp(self.frame_bytes(fn))
        else:
            raise urllib.error.URLError(f"no route {url}")
        return _Resp(json.dumps(body).encode())


class FakeRun:
    """subprocess.run stand-in: records argv/kwargs and the frame files in %05d order, writes out.mp4."""

    def __init__(self, returncode=0, raise_exc=None):
        self.returncode, self.raise_exc = returncode, raise_exc
        self.argv = self.kwargs = self.frames_dir = None
        self.frames = []

    def __call__(self, argv, **kwargs):
        self.argv, self.kwargs = list(argv), dict(kwargs)
        self.frames_dir = os.path.dirname(argv[argv.index("-i") + 1])
        names = sorted(n for n in os.listdir(self.frames_dir) if n.endswith(".png"))
        self.frames = [(n, Path(self.frames_dir, n).read_bytes()) for n in names]
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.returncode == 0:
            Path(argv[-1]).write_bytes(b"\x00\x00\x00\x18ftypisomLOCAL-MP4")
        return subprocess.CompletedProcess(argv, self.returncode)


def _good_probe(path, frames=73):
    return vfp.FrameProbe(path=str(path), frames=frames, packets=frames)


def _transport(fake, run=None, **kw):
    kw.setdefault("frame_probe", _good_probe)
    return T.select_i2v_transport(BACKEND_ID_WAN_22, opener=fake, sleep=lambda s: None,
                                  ffmpeg_exe="ffmpeg-test", ffmpeg_run=run or FakeRun(), **kw)


# ---- workflow -------------------------------------------------------------


def test_wan_workflow_has_no_video_nodes_and_saves_png_frames_from_tiled_decode():
    wf = _wan_wf()
    kinds = [n["class_type"] for n in wf.values()]
    assert "CreateVideo" not in kinds and "SaveVideo" not in kinds
    saves = [k for k, n in wf.items() if n["class_type"] == "SaveImage"]
    assert saves == [A.WAN22_SAVE_IMAGE_NODE]
    save = wf[A.WAN22_SAVE_IMAGE_NODE]
    assert save["inputs"] == {"images": ["8", 0], "filename_prefix": PREFIX}
    assert wf["8"]["class_type"] == "VAEDecodeTiled"
    assert {k: wf["8"]["inputs"][k] for k in ("tile_size", "overlap", "temporal_size", "temporal_overlap")} == {
        "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}
    assert A.wan_frames_encode_spec(wf) == {"node_id": "60", "fps": 24, "expected_frames": 73, "width": W, "height": H}
    native = A.wan_frames_encode_spec(A.build_wan_22_ti2v_workflow(image_filename="s.png", seed=1))
    assert (native["width"], native["height"]) == (A.WAN22_NATIVE_WIDTH, A.WAN22_NATIVE_HEIGHT)
    json.dumps(wf)


def test_svd_graph_is_not_a_frames_graph():
    svd = A.build_svd_xt_workflow(image_filename="s.png", seed=1, frame_count=25, fps=6, motion_bucket_id=127,
                                  decode_temporal_size=8)
    assert A.wan_frames_encode_spec(svd) is None


def test_filename_prefix_is_unique_per_job_and_attempt():
    a = A.wan_frames_filename_prefix("job-1", 1, "aaaaaaaaaaaa")
    assert a.startswith("i2v_wan22_job-1_a1_")
    assert a != A.wan_frames_filename_prefix("job-2", 1, "aaaaaaaaaaaa")
    assert a != A.wan_frames_filename_prefix("job-1", 2, "bbbbbbbbbbbb")
    assert "/" not in A.wan_frames_filename_prefix("../x/y", 1, "r") and "\\" not in A.wan_frames_filename_prefix("a\\b", 1, "r")


class _FakeGpu:
    def free_vram_mib(self):
        return 14000

    def total_vram_mib(self):
        return 16376


def _approved_png():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (64, 112), (10, 120, 10)).save(b, format="PNG")
    return A.SourceImageRef("a" * 64, True, True, True, 64, 112, image_bytes=b.getvalue())


def test_adapter_passes_a_distinct_prefix_on_each_attempt(tmp_path):
    seen = []

    class Flaky:
        def health_check(self):
            return True

        def free_models(self):
            return {"freed": True}

        def submit_and_wait(self, wf):
            seen.append(wf[A.WAN22_SAVE_IMAGE_NODE]["inputs"]["filename_prefix"])
            if len(seen) == 1:
                raise A.InfrastructureFailure("first attempt fails")
            return {"video_bytes": b"ok-bytes", "prompt_id": "p2"}

    ad = A.ImageToVideoAdapter(store=A.VideoJobStore(tmp_path / "s"), transport=Flaky(), gpu_metrics=_FakeGpu())
    ad.generate_video(_approved_png(), seed=3, backend_id=BACKEND_ID_WAN_22, workflow_id="wf-prefix")
    assert len(seen) == 2 and seen[0] != seen[1]
    assert all(p.startswith("i2v_wan22_") for p in seen)
    assert "_a1_" in seen[0] and "_a2_" in seen[1]


# ---- transport -----------------------------------------------------------


def test_frames_fetched_in_frame_index_order_and_encoded_locally(tmp_path, monkeypatch):
    monkeypatch.setattr(T.tempfile, "mkdtemp", lambda prefix="": str(Path(tmp_path, "frames").mkdir() or Path(tmp_path, "frames")))
    counters = list(range(3, 76))  # SaveImage counters need not start at 1; still 73 frames
    items = _items(counters)
    random.Random(4).shuffle(items)  # history list order is not frame order
    preview = {"99": {"images": [{"filename": "other_00001_.png", "subfolder": "", "type": "temp"}]}}
    fake, run = FakeComfy(items, extra_outputs=preview), FakeRun()
    out = _transport(fake, run).submit_and_wait(_wan_wf())

    want = [f"{PREFIX}_{i:05d}_.png" for i in counters]
    assert fake.views == want  # every frame, in frame-index order, only from the SaveImage node
    assert [n for n, _ in run.frames] == [f"{i:05d}.png" for i in range(1, 74)]  # contiguous %05d sequence
    assert [b for _, b in run.frames] == [_png(fn) for fn in want]
    d = run.frames_dir
    assert run.argv == T.build_frames_encode_argv("ffmpeg-test", d, 24, os.path.join(d, "out.mp4"), frames=73)
    # no pipes, bounded, no shell
    assert run.kwargs["stdin"] is subprocess.DEVNULL and run.kwargs["stderr"] is subprocess.STDOUT
    assert run.kwargs["stdout"] not in (subprocess.PIPE, None) and hasattr(run.kwargs["stdout"], "write")
    assert run.kwargs["timeout"] == T.FRAMES_ENCODE_TIMEOUT_S == 300.0
    assert "capture_output" not in run.kwargs and not run.kwargs.get("shell")
    assert out["video_bytes"].startswith(b"\x00\x00\x00\x18ftyp")
    assert out["comfy_output"]["frames"] == 73 and out["comfy_output"]["encoded"] == "local_ffmpeg"
    assert not os.path.exists(d)  # temp frames cleaned up


def test_build_frames_encode_argv_exact():
    assert T.build_frames_encode_argv("ff", "D", 24, "o.mp4", frames=73) == [
        "ff", "-y", "-hide_banner", "-nostdin", "-xerror", "-err_detect", "explode", "-threads", "1",
        "-framerate", "24", "-start_number", "1", "-i", os.path.join("D", "%05d.png"), "-frames:v", "73",
        "-fps_mode", "passthrough", "-threads", "1", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "o.mp4"]
    argv = T.build_frames_encode_argv("ff", "D", 23.976, "o.mp4")
    assert argv[argv.index("-framerate") + 1] == "23.976" and "-frames:v" not in argv


@pytest.mark.parametrize("n", [0, 1, 72])
def test_short_frame_count_is_a_wan_failure_and_never_encodes(n):
    fake, run = FakeComfy(_items(range(1, n + 1))), FakeRun()
    with pytest.raises(T.ComfyJobFailed) as e:
        _transport(fake, run).submit_and_wait(_wan_wf())
    assert isinstance(e.value, A.InfrastructureFailure)
    assert f"saved {n} Wan frames, expected 73" in str(e.value)
    assert run.argv is None and fake.views == []


def test_missing_or_non_png_frame_fails_and_cleans_up(tmp_path, monkeypatch):
    made = []
    real = T.tempfile.mkdtemp
    monkeypatch.setattr(T.tempfile, "mkdtemp", lambda prefix="": made.append(real(prefix=prefix, dir=tmp_path)) or made[-1])
    bad = f"{PREFIX}_00040_.png"
    for payload in (b"", b"<html>not a png"):
        fake = FakeComfy(_items(range(1, 74)), frame_bytes=lambda fn, p=payload: p if fn == bad else _png(fn))
        run = FakeRun()
        with pytest.raises(T.ComfyJobFailed, match="missing or not a PNG"):
            _transport(fake, run).submit_and_wait(_wan_wf())
        assert run.argv is None
    assert made and not any(os.path.exists(m) for m in made)


@pytest.mark.parametrize("run,match", [
    (FakeRun(returncode=1), r"failed \(exit 1\)"),
    (FakeRun(raise_exc=subprocess.TimeoutExpired(["ffmpeg"], 300)), "timed out after 300s"),
    (FakeRun(raise_exc=FileNotFoundError("no ffmpeg")), "could not start"),
])
def test_ffmpeg_failure_is_a_wan_failure_and_cleans_up(run, match):
    with pytest.raises(T.ComfyJobFailed, match=match):
        _transport(FakeComfy(_items(range(1, 74))), run).submit_and_wait(_wan_wf())
    assert run.argv is not None and not os.path.exists(run.frames_dir)


def test_no_ffmpeg_available_is_a_wan_failure(monkeypatch):
    monkeypatch.setattr(T, "resolve_ffmpeg", lambda: None)
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=FakeComfy(_items(range(1, 74))), sleep=lambda s: None)
    with pytest.raises(T.ComfyJobFailed, match="ffmpeg not available"):
        tr.submit_and_wait(_wan_wf())


def test_video_output_graph_keeps_the_old_download_path():
    fake = FakeComfy([{"filename": "svd_00001.mp4", "subfolder": "", "type": "output"}], node="9")
    fake.frame_bytes = lambda fn: b"\x00\x00\x00\x18ftypmp42SVD"
    run = FakeRun()
    out = _transport(fake, run).submit_and_wait({"1": {"class_type": "X"}})
    assert out["video_bytes"].endswith(b"SVD") and run.argv is None and fake.views == ["svd_00001.mp4"]


def test_short_frames_go_through_the_adapter_infra_retry_path(tmp_path):
    fake, run = FakeComfy(_items(range(1, 73))), FakeRun()
    ad = A.ImageToVideoAdapter(store=A.VideoJobStore(tmp_path / "s"), transport=_transport(fake, run),
                               gpu_metrics=_FakeGpu())
    res = ad.generate_video(_approved_png(), seed=5, backend_id=BACKEND_ID_WAN_22, workflow_id="wf-short",
                           motion_plan={"length": 73})  # chapter clips ask Wan for 73 frames
    assert res.validation_status == A.ValidationStatus.INFRA_FAILURE.value
    assert "expected 73" in (res.failure_reason or "")
    assert fake.prompts == A.MAX_INFRASTRUCTURE_ATTEMPTS  # same bounded retry as any Wan infra failure
    assert run.argv is None


@pytest.mark.skipif(not (T.resolve_ffmpeg() and shutil.which("ffprobe")), reason="needs ffmpeg + ffprobe")
def test_real_ffmpeg_encodes_73_frames_at_24fps(tmp_path):
    from PIL import Image

    def frame(fn):
        i = int(fn.rsplit("_", 2)[-2])
        b = io.BytesIO()
        Image.new("RGB", (64, 112), (i * 3 % 256, 40, 200)).save(b, format="PNG")
        return b.getvalue()

    fake = FakeComfy(_items(range(1, 74)), frame_bytes=frame)
    tr = T.select_i2v_transport(BACKEND_ID_WAN_22, opener=fake, sleep=lambda s: None)
    out = tr.submit_and_wait(_wan_wf())
    assert out["comfy_output"]["frames_probed"] == 73 and out["comfy_output"]["pts_missing"] == []
    mp4 = tmp_path / "o.mp4"
    mp4.write_bytes(out["video_bytes"])
    probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-select_streams", "v:0",
                            "-show_entries", "stream=nb_read_frames,r_frame_rate,codec_name,pix_fmt",
                            "-of", "json", str(mp4)], capture_output=True, text=True, timeout=60, check=True)
    s = json.loads(probe.stdout)["streams"][0]
    assert (s["codec_name"], s["pix_fmt"], s["r_frame_rate"], int(s["nb_read_frames"])) == ("h264", "yuv420p", "24/1", 73)