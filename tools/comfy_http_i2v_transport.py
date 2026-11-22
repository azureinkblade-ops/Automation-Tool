"""Comfy HTTP I2V transport (additive; implements I2VBackendTransport).

Out-of-process urllib client for a running ComfyUI: POST /prompt, poll
/history/<id>, download outputs via /view. Fail-closed: unreachable endpoint
or missing required models raise ComfyTransportUnavailable / ComfyModelsMissing
(subclasses of InfrastructureFailure) -- never a placeholder video.

Wan 2.2 graphs save PNG frames (SaveImage) instead of a video, because ComfyUI's own
CreateVideo/SaveVideo step crashed ComfyUI while encoding. For those graphs this transport
fetches every frame via /view in frame-index order, checks the count, and encodes the mp4
locally with ffmpeg (no pipes, bounded by a timeout, temp frames always removed). Missing or
short frames and ffmpeg failures raise ComfyJobFailed, i.e. an ordinary Wan failure that goes
through the normal retry / SVD-fallback path. Graphs with a video output (SVD) are unchanged.

Opt-in for wan_22 only via select_i2v_transport(); SVD default path is untouched
(returns None -> caller keeps its existing transport). GPU ownership stays with
ImageToVideoAdapter's ExclusiveGpuLease.KIND_I2V; this transport never acquires it.
No identity canon, no LIVE_PUBLISH, no NET-PATREON, no chapter allocation.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from tools.i2v_backend_registry import BACKEND_ID_WAN_22
from tools.i2v_production_adapter import InfrastructureFailure, wan_frames_encode_spec

IDENTITY_CANON = False
COMFY_I2V_URL_ENV = "COMFY_I2V_URL"
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"

WAN_22_REQUIRED_MODELS: Dict[str, str] = {
    "wan2.2_ti2v_5B_fp16.safetensors": "diffusion_models",
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors": "text_encoders",
    "wan2.2_vae.safetensors": "vae",
}
_VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".gif", ".webp")
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
# SaveImage names frames "<prefix>_<counter:05>_.png"; the counter is the frame index.
_FRAME_INDEX_RE = re.compile(r"_(\d+)_?\.png$", re.IGNORECASE)
FRAMES_ENCODE_TIMEOUT_S = 300.0


class ComfyTransportUnavailable(InfrastructureFailure):
    pass


class ComfyModelsMissing(InfrastructureFailure):
    pass


class ComfyJobFailed(InfrastructureFailure):
    pass


class ComfyUploadFailed(InfrastructureFailure):
    pass


Opener = Callable[..., Any]


class ComfyHttpI2VTransport:
    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        timeout: float = 10.0,
        poll_interval: float = 2.0,
        max_wait_s: float = 1800.0,
        required_models: Optional[Mapping[str, str]] = None,
        opener: Opener = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        ffmpeg_exe: Optional[str] = None,
        ffmpeg_run: Callable[..., Any] = subprocess.run,
        encode_timeout_s: float = FRAMES_ENCODE_TIMEOUT_S,
    ) -> None:
        self.base_url = (base_url or os.environ.get(COMFY_I2V_URL_ENV) or DEFAULT_COMFY_URL).rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_wait_s = max_wait_s
        self.required_models = dict(required_models or {})
        self._open = opener
        self._sleep = sleep
        self._clock = clock
        self._ffmpeg_exe = ffmpeg_exe
        self._ffmpeg_run = ffmpeg_run
        self.encode_timeout_s = float(encode_timeout_s)
        self.client_id = uuid.uuid4().hex

    # -- http ---------------------------------------------------------
    def _req(self, path: str, payload: Optional[Dict[str, Any]] = None, raw: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with self._open(req, timeout=self.timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            raise ComfyJobFailed(f"comfy HTTP {e.code} on {path}: {detail}") from e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise ComfyTransportUnavailable(f"comfy unreachable at {self.base_url}: {e}") from e
        if raw:
            return body
        return json.loads(body.decode("utf-8")) if body else {}

    # -- protocol -----------------------------------------------------
    def health_check(self) -> bool:
        try:
            self._req("/system_stats")
            return True
        except InfrastructureFailure:
            return False

    def free_models(self) -> Dict[str, Any]:
        try:
            self._req("/free", {"unload_models": True, "free_memory": True})
            return {"freed": True}
        except InfrastructureFailure as e:
            return {"freed": False, "error": str(e)}

    def missing_models(self) -> List[str]:
        missing: List[str] = []
        cache: Dict[str, Iterable[str]] = {}
        for name, folder in self.required_models.items():
            if folder not in cache:
                listing = self._req(f"/models/{urllib.parse.quote(folder)}")
                cache[folder] = set(listing or [])
            if name not in cache[folder]:
                missing.append(f"{folder}/{name}")
        return missing

    def assert_ready(self) -> None:
        if not self.health_check():
            raise ComfyTransportUnavailable(f"comfy unreachable at {self.base_url}")
        missing = self.missing_models()
        if missing:
            raise ComfyModelsMissing("comfy models missing: " + ", ".join(missing))

    def upload_image(self, png_bytes: bytes, filename: str, *, overwrite: bool = True) -> str:
        """POST /upload/image (multipart). Returns LoadImage name. Fail-closed."""
        if not png_bytes:
            raise ComfyUploadFailed("upload_image: empty bytes")
        boundary = "----comfyi2v" + uuid.uuid4().hex
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
            "Content-Type: image/png\r\n\r\n".encode() + png_bytes + b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\n"
            f"{'true' if overwrite else 'false'}\r\n".encode(),
            f"--{boundary}--\r\n".encode(),
        ]
        req = urllib.request.Request(f"{self.base_url}/upload/image", data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                                     method="POST")
        try:
            with self._open(req, timeout=self.timeout) as r:
                resp = json.loads(r.read().decode("utf-8") or "{}")
        except Exception as e:  # noqa: BLE001 - every failure is fail-closed
            raise ComfyUploadFailed(f"comfy /upload/image failed at {self.base_url}: {e}") from e
        name = resp.get("name") if isinstance(resp, dict) else None
        if not name:
            raise ComfyUploadFailed(f"comfy /upload/image returned no name: {resp}")
        sub = resp.get("subfolder") or ""
        return f"{sub}/{name}" if sub else str(name)

    def stage_and_upload(self, source_image: Any, target_width: int, target_height: int, job_id: str) -> str:
        """FIT_INSIDE letterbox the approved still to native dims and upload. Fail-closed."""
        raw = getattr(source_image, "image_bytes", None)
        path = getattr(source_image, "source_path", None)
        try:
            if not raw and path:
                with open(path, "rb") as fh:
                    raw = fh.read()
            if not raw:
                raise ComfyUploadFailed("stage_and_upload: no image bytes")
            png = letterbox_png(raw, int(target_width), int(target_height))
        except ComfyUploadFailed:
            raise
        except Exception as e:  # noqa: BLE001
            raise ComfyUploadFailed(f"stage_and_upload: letterbox failed: {e}") from e
        safe = "".join(c for c in str(job_id) if c.isalnum() or c in "-_")[:64] or "job"
        return self.upload_image(png, f"i2v_src_{safe}.png")

    def submit_and_wait(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        self.assert_ready()
        resp = self._req("/prompt", {"prompt": workflow, "client_id": self.client_id})
        if resp.get("node_errors"):
            raise ComfyJobFailed(f"comfy node_errors: {json.dumps(resp['node_errors'])[:500]}")
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            raise ComfyJobFailed(f"comfy /prompt returned no prompt_id: {resp}")
        deadline = self._clock() + self.max_wait_s
        entry: Optional[Dict[str, Any]] = None
        while True:
            hist = self._req(f"/history/{prompt_id}")
            entry = hist.get(prompt_id) if isinstance(hist, dict) else None
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    raise ComfyJobFailed(f"comfy job {prompt_id} error: {json.dumps(status)[:500]}")
                if status.get("completed", True) and entry.get("outputs"):
                    break
            if self._clock() >= deadline:
                raise ComfyJobFailed(f"comfy job {prompt_id} timed out after {self.max_wait_s}s")
            self._sleep(self.poll_interval)
        frames_spec = wan_frames_encode_spec(workflow)
        if frames_spec is not None:
            return self._frames_to_video(prompt_id, entry.get("outputs") or {}, frames_spec)
        ref = _pick_video_output(entry.get("outputs") or {})
        if ref is None:
            raise ComfyJobFailed(f"comfy job {prompt_id} produced no video output")
        q = urllib.parse.urlencode({"filename": ref["filename"], "subfolder": ref.get("subfolder", ""),
                                    "type": ref.get("type", "output")})
        video_bytes = self._req(f"/view?{q}", raw=True)
        if not video_bytes:
            raise ComfyJobFailed(f"comfy job {prompt_id} empty video download")
        return {
            "prompt_id": prompt_id,
            "video_bytes": video_bytes,
            "comfy_output": ref,
            "identity_canon": False,
        }

    # -- Wan PNG frames -> local mp4 --------------------------------------
    def _frames_to_video(self, prompt_id: str, outputs: Mapping[str, Any], spec: Mapping[str, Any]) -> Dict[str, Any]:
        frames = pick_frame_outputs(outputs, spec["node_id"])
        expected = int(spec["expected_frames"])
        if len(frames) != expected:
            raise ComfyJobFailed(f"comfy job {prompt_id} saved {len(frames)} Wan frames, expected {expected}")
        ffmpeg = self._ffmpeg_exe or resolve_ffmpeg()
        if not ffmpeg:
            raise ComfyJobFailed("ffmpeg not available for the local Wan frame encode")
        tmp = tempfile.mkdtemp(prefix="wan22_frames_")
        try:
            for i, ref in enumerate(frames, start=1):
                q = urllib.parse.urlencode({"filename": ref["filename"], "subfolder": ref.get("subfolder", ""),
                                            "type": ref.get("type", "output")})
                data = self._req(f"/view?{q}", raw=True)
                if not data or not bytes(data).startswith(_PNG_SIG):
                    raise ComfyJobFailed(f"comfy job {prompt_id} frame {ref['filename']} missing or not a PNG")
                with open(os.path.join(tmp, f"{i:05d}.png"), "wb") as fh:
                    fh.write(data)
            out_path = os.path.join(tmp, "out.mp4")
            argv = build_frames_encode_argv(ffmpeg, tmp, spec["fps"], out_path)
            log_path = os.path.join(tmp, "ffmpeg.log")
            try:
                with open(log_path, "wb") as log:
                    kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT,
                                          "timeout": self.encode_timeout_s, "check": False}
                    if os.name == "nt":
                        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    proc = self._ffmpeg_run(argv, **kw)
            except subprocess.TimeoutExpired as e:
                raise ComfyJobFailed(f"ffmpeg Wan frame encode timed out after {self.encode_timeout_s:g}s") from e
            except OSError as e:
                raise ComfyJobFailed(f"ffmpeg Wan frame encode could not start: {e}") from e
            rc = getattr(proc, "returncode", 1)
            if rc != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
                raise ComfyJobFailed(f"ffmpeg Wan frame encode failed (exit {rc}): {_tail(log_path)}")
            with open(out_path, "rb") as fh:
                video_bytes = fh.read()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {
            "prompt_id": prompt_id,
            "video_bytes": video_bytes,
            "comfy_output": {
                "frames": len(frames),
                "first_frame": frames[0]["filename"],
                "last_frame": frames[-1]["filename"],
                "fps": spec["fps"],
                "encoded": "local_ffmpeg",
            },
            "identity_canon": False,
        }


def resolve_ffmpeg() -> Optional[str]:
    """Same lookup as the presentation step that renders this clip next (FFMPEG_PATH, else PATH)."""
    return os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")


def build_frames_encode_argv(ffmpeg: str, frames_dir: str, fps: Any, out_path: str) -> List[str]:
    """ffmpeg -y -framerate <fps> -i <dir>/%05d.png -c:v libx264 -pix_fmt yuv420p <out>."""
    f = float(fps)
    rate = str(int(f)) if f.is_integer() else repr(f)
    return [str(ffmpeg), "-y", "-framerate", rate, "-i", os.path.join(str(frames_dir), "%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)]


def pick_frame_outputs(outputs: Mapping[str, Any], node_id: str) -> List[Dict[str, Any]]:
    """PNG frames saved by the SaveImage node, ordered by frame index (not by list order)."""
    node_out = outputs.get(str(node_id)) if isinstance(outputs, Mapping) else None
    items = (node_out.get("images") or []) if isinstance(node_out, Mapping) else []
    indexed: Dict[int, Dict[str, Any]] = {}
    for item in items:
        fn = str((item or {}).get("filename", ""))
        m = _FRAME_INDEX_RE.search(fn)
        if not m:
            raise ComfyJobFailed(f"unexpected Wan frame name {fn!r}")
        idx = int(m.group(1))
        if idx in indexed:
            raise ComfyJobFailed(f"duplicate Wan frame index {idx} ({fn!r})")
        indexed[idx] = dict(item)
    return [indexed[k] for k in sorted(indexed)]


def _tail(path: str, n: int = 400) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read()[-n:].decode("utf-8", "replace")
    except OSError:
        return ""


def letterbox_png(raw: bytes, tw: int, th: int) -> bytes:
    """FIT_INSIDE + black letterbox (no crop/stretch) -> PNG bytes."""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    scale = min(tw / im.width, th / im.height)
    sw, sh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    canvas.paste(im.resize((sw, sh), Image.Resampling.LANCZOS), ((tw - sw) // 2, (th - sh) // 2))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _pick_video_output(outputs: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    for node_out in outputs.values():
        if not isinstance(node_out, Mapping):
            continue
        for key in ("videos", "gifs", "images"):
            for item in node_out.get(key) or []:
                fn = str(item.get("filename", ""))
                if fn.lower().endswith(_VIDEO_EXT):
                    return dict(item)
    return None


def select_i2v_transport(backend_id: str, *, base_url: Optional[str] = None, **kw: Any) -> Optional[ComfyHttpI2VTransport]:
    """wan_22 -> ComfyHttpI2VTransport with Wan model preflight. Others -> None (SVD unchanged)."""
    if backend_id != BACKEND_ID_WAN_22:
        return None
    kw.setdefault("required_models", WAN_22_REQUIRED_MODELS)
    return ComfyHttpI2VTransport(base_url, **kw)
