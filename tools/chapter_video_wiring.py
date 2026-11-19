"""CHAPTER_VIDEO_WIRING -- production video for chapter Reel/Short packs.

Wan 2.2 (default) -> SVD-XT 1.1 (fallback) -> MEDIA_HOLD, built on the stage-1
media pipeline (tools.media_pipeline_i2v_wiring / media_pipeline_integration).

Flow for one approved still (``produce_chapter_clip``)::

    config check -> ComfyUI guard (launcher -Status must say dynvram_disabled=True)
      -> Wan 2.2 via ComfyHttpI2VTransport (ExclusiveGpuLease KIND_I2V, media gate >= min s)
      -> on any failure: SVD-XT 1.1 (same gates)
      -> no valid clip: MEDIA_HOLD (never the still, never an old/banked clip)

One switch: env ``CHAPTER_VIDEO_BACKEND``
    wan_22 (default)  Wan first, SVD fallback
    svd_xt_1_1        SVD only (the one-line revert from Wan)
    off               wiring disabled: the legacy FFmpeg slideshow builder is untouched

Tunables (all optional): CHAPTER_VIDEO_FRAMES (73, must be 4n+1), CHAPTER_VIDEO_FPS (24),
CHAPTER_VIDEO_MIN_SECONDS (3.0, floored at 3.0), CHAPTER_VIDEO_LOOP_FALLBACK (0; explicit
opt-in ffmpeg loop of a too-short clip), CHAPTER_VIDEO_MIN_FREE_VRAM_MIB (0 = as in the
passing Wan health check), CHAPTER_VIDEO_MAX_WAIT_S (1200), CHAPTER_VIDEO_COMFY_LAUNCHER,
CHAPTER_VIDEO_STOP_COMFY_AFTER (1: stop ComfyUI only if this run started it),
CHAPTER_VIDEO_COMFY_IDLE_RESTART (1: an already-running ComfyUI is restarted through the launcher
only when GET /queue shows it idle; 0 = legacy reuse), COMFY_I2V_URL.

ComfyUI lifecycle (all through ``start_comfyui_wan.bat``, always re-checked with ``-Status``):
  * port busy + queue idle  -> launcher ``-Stop`` (it verifies its own pid file + command line and
    never touches anything else), then a fresh start, then ``-Status`` dynvram_disabled=True.
  * port busy + queue busy / unknown / instance not stoppable -> MEDIA_HOLD; a busy instance is never stopped.
  * port free -> one start via the launcher.
  * an attempt that fails while the launcher reports the port FREE (ComfyUI died / crashed loading the
    model) -> one fresh start via the launcher and ONE retry of the same backend (then the normal
    fallback chain). A still-alive instance that merely errors is never restarted.
Every subprocess here is built as an argv LIST (no shell=True, no joined command strings), so paths
with spaces (e.g. a repo folder called 'Automation tool') are safe.

Hard rules kept here: ComfyUI is only ever started through the launcher .bat and only
used once ``-Status`` reports dynvram_disabled=True; a second ComfyUI is never started on
8188; no GPU work happens at import/build time; no identity-canon writes; no publishing.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from tools import i2v_backend_registry as reg
from tools import i2v_presentation_adapter as pa
from tools import i2v_production_adapter as i2v
from tools import media_pipeline_i2v_wiring as wiring
from tools.comfy_http_i2v_transport import (
    DEFAULT_COMFY_URL,
    WAN_22_REQUIRED_MODELS,
    ComfyHttpI2VTransport,
)
from tools.media_pipeline_integration import (
    ApprovedStillRef,
    MediaPipeline,
    PipelineOutcome,
    VIDEO_CREATES_IDENTITY_CANON,
)
from tools.media_validity import (
    MIN_SOCIAL_VIDEO_SECONDS,
    probe_presented_video,
    validate_presented_social_video,
)

WIRING_VERSION = "chapter_video_wiring_v2"

ENV_BACKEND = "CHAPTER_VIDEO_BACKEND"
ENV_FRAMES = "CHAPTER_VIDEO_FRAMES"
ENV_FPS = "CHAPTER_VIDEO_FPS"
ENV_MIN_SECONDS = "CHAPTER_VIDEO_MIN_SECONDS"
ENV_LOOP = "CHAPTER_VIDEO_LOOP_FALLBACK"
ENV_MIN_FREE_VRAM = "CHAPTER_VIDEO_MIN_FREE_VRAM_MIB"
ENV_MAX_WAIT = "CHAPTER_VIDEO_MAX_WAIT_S"
ENV_LAUNCHER = "CHAPTER_VIDEO_COMFY_LAUNCHER"
ENV_STOP_AFTER = "CHAPTER_VIDEO_STOP_COMFY_AFTER"
ENV_IDLE_RESTART = "CHAPTER_VIDEO_COMFY_IDLE_RESTART"

BACKEND_OFF = "off"
DEFAULT_BACKEND = reg.BACKEND_ID_WAN_22
DEFAULT_FRAMES = 73  # 4n+1; 73 / 24 fps = 3.04 s
DEFAULT_FPS = 24
DEFAULT_LAUNCHER = r"C:\Users\David\ComfyUI-Launch\start_comfyui_wan.bat"
SVD_REQUIRED_MODELS: Dict[str, str] = {"svd_xt_1_1.safetensors": "checkpoints"}

MEDIA_HOLD = PipelineOutcome.MEDIA_HOLD.value
SOCIAL_READY = PipelineOutcome.SOCIAL_READY.value

_BACKEND_ALIASES = {
    "": DEFAULT_BACKEND,
    "wan": reg.BACKEND_ID_WAN_22,
    "wan22": reg.BACKEND_ID_WAN_22,
    "wan_22": reg.BACKEND_ID_WAN_22,
    "wan2.2": reg.BACKEND_ID_WAN_22,
    "svd": reg.BACKEND_ID_SVD_XT_1_1,
    "svd_xt": reg.BACKEND_ID_SVD_XT_1_1,
    "svd_xt_1_1": reg.BACKEND_ID_SVD_XT_1_1,
    "off": BACKEND_OFF,
    "none": BACKEND_OFF,
    "legacy": BACKEND_OFF,
    "slideshow": BACKEND_OFF,
}
_TRUTHY = {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


def _env_int(env: Mapping[str, str], name: str, default: int, problems: List[str]) -> int:
    raw = str(env.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        problems.append(f"{name}_not_an_integer:{raw[:20]}")
        return default


def _env_float(env: Mapping[str, str], name: str, default: float, problems: List[str]) -> float:
    raw = str(env.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        problems.append(f"{name}_not_a_number:{raw[:20]}")
        return default


@dataclass(frozen=True)
class ChapterVideoConfig:
    backend: str = DEFAULT_BACKEND
    frames: int = DEFAULT_FRAMES
    fps: int = DEFAULT_FPS
    min_seconds: float = MIN_SOCIAL_VIDEO_SECONDS
    loop_fallback: bool = False
    min_free_vram_mib: int = 0
    comfy_url: str = DEFAULT_COMFY_URL
    max_wait_s: float = 1200.0
    comfy_launcher: str = DEFAULT_LAUNCHER
    stop_comfy_after: bool = True
    idle_restart: bool = True
    problems: Tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.backend != BACKEND_OFF

    @property
    def backend_order(self) -> List[str]:
        """Wan -> SVD fallback; SVD-only when SVD is the chosen backend."""
        if self.backend == reg.BACKEND_ID_WAN_22:
            return [reg.BACKEND_ID_WAN_22, reg.BACKEND_ID_SVD_XT_1_1]
        if self.backend == reg.BACKEND_ID_SVD_XT_1_1:
            return [reg.BACKEND_ID_SVD_XT_1_1]
        return []

    @property
    def wan_clip_seconds(self) -> float:
        return self.frames / float(self.fps) if self.fps > 0 else 0.0

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "ChapterVideoConfig":
        env = os.environ if env is None else env
        problems: List[str] = []
        raw_backend = str(env.get(ENV_BACKEND, "") or "").strip().lower()
        backend = _BACKEND_ALIASES.get(raw_backend)
        if backend is None:
            problems.append(f"unknown_{ENV_BACKEND}:{raw_backend[:30]}")
            backend = raw_backend  # kept so callers can report it; produce_chapter_clip holds
        frames = _env_int(env, ENV_FRAMES, DEFAULT_FRAMES, problems)
        fps = _env_int(env, ENV_FPS, DEFAULT_FPS, problems)
        min_seconds = max(_env_float(env, ENV_MIN_SECONDS, MIN_SOCIAL_VIDEO_SECONDS, problems), MIN_SOCIAL_VIDEO_SECONDS)
        loop = str(env.get(ENV_LOOP, "") or "").strip().lower() in _TRUTHY
        stop_raw = str(env.get(ENV_STOP_AFTER, "") or "").strip().lower()
        stop_after = True if stop_raw == "" else stop_raw in _TRUTHY
        idle_raw = str(env.get(ENV_IDLE_RESTART, "") or "").strip().lower()
        idle_restart = True if idle_raw == "" else idle_raw in _TRUTHY
        cfg = cls(
            backend=backend,
            frames=frames,
            fps=fps,
            min_seconds=min_seconds,
            loop_fallback=loop,
            min_free_vram_mib=max(0, _env_int(env, ENV_MIN_FREE_VRAM, 0, problems)),
            comfy_url=str(env.get("COMFY_I2V_URL", "") or DEFAULT_COMFY_URL).strip() or DEFAULT_COMFY_URL,
            max_wait_s=max(30.0, _env_float(env, ENV_MAX_WAIT, 1200.0, problems)),
            comfy_launcher=str(env.get(ENV_LAUNCHER, "") or DEFAULT_LAUNCHER).strip() or DEFAULT_LAUNCHER,
            stop_comfy_after=stop_after,
            idle_restart=idle_restart,
        )
        problems.extend(cfg._frame_problems())
        return dataclasses.replace(cfg, problems=tuple(problems))

    def _frame_problems(self) -> List[str]:
        out: List[str] = []
        if self.backend != reg.BACKEND_ID_WAN_22:
            return out
        if self.frames < 5 or (self.frames - 1) % 4 != 0:
            out.append(f"frames_not_4n_plus_1:{self.frames}")
        if self.fps < 1:
            out.append(f"fps_invalid:{self.fps}")
        elif not self.loop_fallback and self.wan_clip_seconds + 1e-6 < self.min_seconds:
            out.append(
                f"clip_shorter_than_min:{self.frames}f@{self.fps}fps={self.wan_clip_seconds:.2f}s<{self.min_seconds:.2f}s"
            )
        return out


# --------------------------------------------------------------------------- #
# ComfyUI guard (launcher only; never a second server)
# --------------------------------------------------------------------------- #

LauncherRunner = Callable[[Sequence[str], float], Tuple[int, str]]


def default_launcher_runner(args: Sequence[str], timeout: float) -> Tuple[int, str]:
    proc = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, check=False)
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


@dataclass
class LauncherStatus:
    port_busy: Optional[bool] = None
    dynvram_disabled: Optional[bool] = None
    reachable: bool = False


def parse_launcher_status(text: str) -> LauncherStatus:
    """Parse ``start_comfyui_wan.bat -Status`` output (port8188_busy=..., dynvram_disabled=...)."""
    st = LauncherStatus()
    m = re.search(r"port\d+_busy=(True|False)", text or "")
    if m:
        st.port_busy = m.group(1) == "True"
    m = re.search(r"dynvram_disabled=(True|False)", text or "")
    if m:
        st.dynvram_disabled = m.group(1) == "True"
    st.reachable = bool(m) and "unreachable" not in (text or "")
    return st


@dataclass
class ComfyReady:
    ok: bool
    started_by_us: bool = False
    reason: str = ""


QueueProbe = Callable[[str, float], Optional[Tuple[int, int]]]


def launcher_argv(launcher: str, *flags: str) -> List[str]:
    """argv LIST for the launcher .bat (never a joined string; the path may contain spaces)."""
    return [str(launcher), *flags]


def default_queue_probe(base_url: str, timeout: float = 8.0) -> Optional[Tuple[int, int]]:
    """GET ``{base_url}/queue`` -> (running, pending) job counts; None if unreachable / unparseable."""
    import urllib.request

    try:
        with urllib.request.urlopen(str(base_url).rstrip("/") + "/queue", timeout=timeout) as resp:  # noqa: S310 (local ComfyUI)
            data = json.loads(resp.read().decode("utf-8", "replace"))
        if not isinstance(data, dict):
            return None
        return len(data.get("queue_running") or []), len(data.get("queue_pending") or [])
    except Exception:  # noqa: BLE001
        return None


def _launcher_status(cfg: ChapterVideoConfig, runner: LauncherRunner) -> Tuple[Optional[LauncherStatus], str]:
    try:
        rc, out = runner(launcher_argv(cfg.comfy_launcher, "-Status"), 90.0)
    except Exception as exc:  # noqa: BLE001
        return None, f"COMFY_STATUS_ERROR:{type(exc).__name__}:{str(exc)[:120]}"
    st = parse_launcher_status(out)
    if st.port_busy is None:
        return None, f"COMFY_STATUS_UNPARSEABLE:rc={rc}"
    return st, ""


def start_comfy_via_launcher(cfg: ChapterVideoConfig, runner: LauncherRunner = default_launcher_runner) -> ComfyReady:
    """Start exactly ONE ComfyUI through the launcher .bat (caller has confirmed the port is free), then
    require ``-Status`` dynvram_disabled=True. Never starts anything but via the launcher."""
    bat = cfg.comfy_launcher
    try:
        rc, out = runner(launcher_argv(bat), 480.0)
    except Exception as exc:  # noqa: BLE001
        stop_comfy_started_by_us(cfg, runner)
        return ComfyReady(False, reason=f"COMFY_START_ERROR:{type(exc).__name__}:{str(exc)[:120]}")
    if rc != 0:
        # rc 3 = another ComfyUI / busy port (not ours: never stop). Others may have left ours running.
        if rc != 3:
            stop_comfy_started_by_us(cfg, runner)
        return ComfyReady(False, reason=f"COMFY_START_FAILED:rc={rc}")
    try:
        rc2, out2 = runner(launcher_argv(bat, "-Status"), 90.0)
    except Exception as exc:  # noqa: BLE001
        stop_comfy_started_by_us(cfg, runner)
        return ComfyReady(False, started_by_us=False, reason=f"COMFY_STATUS_ERROR:{type(exc).__name__}")
    st2 = parse_launcher_status(out2)
    if st2.dynvram_disabled is not True:
        stop_comfy_started_by_us(cfg, runner)
        return ComfyReady(False, reason="COMFY_DYNVRAM_NOT_DISABLED_AFTER_START")
    return ComfyReady(True, started_by_us=True, reason="started_via_launcher")


def _wait_port_free(
    cfg: ChapterVideoConfig, runner: LauncherRunner, sleep: Callable[[float], Any], tries: int = 6, delay: float = 2.0
) -> Optional[bool]:
    """True once the launcher reports the port free; False if still busy after ``tries``; None if status unusable."""
    for i in range(max(1, tries)):
        st, _err = _launcher_status(cfg, runner)
        if st is None:
            return None
        if st.port_busy is False:
            return True
        if i + 1 < tries:
            sleep(delay)
    return False


def _restart_idle_instance(
    cfg: ChapterVideoConfig, runner: LauncherRunner, queue_probe: QueueProbe, sleep: Callable[[float], Any]
) -> ComfyReady:
    """Port busy by a ComfyUI this run did not start: restart it through the launcher ONLY if it is idle."""
    try:
        queue = queue_probe(cfg.comfy_url, 8.0)
    except Exception:  # noqa: BLE001
        queue = None
    if queue is None:
        return ComfyReady(False, reason="COMFY_BUSY_PORT_QUEUE_UNKNOWN_NOT_RESTARTED")
    running, pending = int(queue[0]), int(queue[1])
    if running or pending:
        return ComfyReady(False, reason=f"COMFY_BUSY_NOT_RESTARTED:running={running},pending={pending}")
    # Idle. The launcher's -Stop verifies its own pid file + command line; anything else is left alone (rc 1).
    try:
        stop_rc, _out = runner(launcher_argv(cfg.comfy_launcher, "-Stop"), 90.0)
    except Exception as exc:  # noqa: BLE001
        return ComfyReady(False, reason=f"COMFY_STOP_ERROR:{type(exc).__name__}:{str(exc)[:120]}")
    if stop_rc != 0:
        return ComfyReady(False, reason=f"COMFY_IDLE_INSTANCE_NOT_STOPPABLE_BY_LAUNCHER:rc={stop_rc}")
    free = _wait_port_free(cfg, runner, sleep)
    if free is not True:
        return ComfyReady(False, reason="COMFY_IDLE_RESTART_PORT_STILL_BUSY" if free is False else "COMFY_STATUS_UNUSABLE_AFTER_STOP")
    res = start_comfy_via_launcher(cfg, runner)
    if res.ok:
        res.reason = "restarted_idle_instance_via_launcher"
    return res


def ensure_comfy_ready(
    cfg: ChapterVideoConfig,
    runner: LauncherRunner = default_launcher_runner,
    queue_probe: QueueProbe = default_queue_probe,
    sleep: Callable[[float], Any] = time.sleep,
) -> ComfyReady:
    """Get ONE ComfyUI that reports dynvram_disabled=True, only ever via the launcher.

    * port free            -> start via the launcher.
    * port busy, idle      -> launcher ``-Stop`` + fresh start (``idle_restart``; else legacy reuse).
    * port busy, busy/unknown queue or not stoppable -> not-ok (caller holds the media). Never a second server.
    """
    st, err = _launcher_status(cfg, runner)
    if st is None:
        return ComfyReady(False, reason=err)
    if st.port_busy:
        if cfg.idle_restart:
            return _restart_idle_instance(cfg, runner, queue_probe, sleep)
        if st.dynvram_disabled is True:
            return ComfyReady(True, started_by_us=False, reason="reused_running_comfyui")
        return ComfyReady(False, reason="COMFY_PORT_BUSY_DYNVRAM_NOT_CONFIRMED")
    return start_comfy_via_launcher(cfg, runner)


def restart_comfy_if_gone(
    cfg: ChapterVideoConfig, runner: LauncherRunner = default_launcher_runner
) -> ComfyReady:
    """After a failed attempt: if (and only if) the launcher reports the port FREE (ComfyUI died / crashed),
    start a fresh instance via the launcher. A still-alive instance is never touched."""
    st, err = _launcher_status(cfg, runner)
    if st is None:
        return ComfyReady(False, reason=err)
    if st.port_busy:
        return ComfyReady(False, reason=COMFY_STILL_ALIVE)
    res = start_comfy_via_launcher(cfg, runner)
    if res.ok:
        res.reason = "restarted_after_crash_via_launcher"
    return res


COMFY_STILL_ALIVE = "COMFY_STILL_ALIVE_NOT_RESTARTED"


def stop_comfy_started_by_us(cfg: ChapterVideoConfig, runner: LauncherRunner = default_launcher_runner) -> None:
    """``-Stop`` only ever stops the process the launcher itself started (pid file + cmdline verified)."""
    try:
        runner(launcher_argv(cfg.comfy_launcher, "-Stop"), 90.0)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Optional loop render (explicit opt-in, off by default)
# --------------------------------------------------------------------------- #


def build_loop_ffmpeg_argv(ffmpeg: str, src: "os.PathLike[str] | str", out_path: "os.PathLike[str] | str",
                           extra_loops: int, vf: str) -> List[str]:
    """argv LIST for the opt-in loop render (paths with spaces stay single elements)."""
    return [str(ffmpeg), "-y", "-stream_loop", str(int(extra_loops)), "-i", str(src), "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out_path)]


class LoopingRender:
    """RenderFn: default FIT_INSIDE ffmpeg render, but loop a too-short source up to ``min_seconds``."""

    def __init__(self, min_seconds: float, probe: Callable[[Path], Any] = probe_presented_video) -> None:
        self.min_seconds = float(min_seconds)
        self._probe = probe
        self.looped = False

    def __call__(self, clip: Any, transform: Any, out_path: Path) -> bytes:
        src = Path(clip.video_path)
        info = self._probe(src)
        dur = float(getattr(info, "duration", 0.0) or 0.0)
        if dur <= 0:
            raise pa.PresentationError("loop render: source duration unknown")
        if dur + 1e-6 >= self.min_seconds:
            return pa.default_ffmpeg_render(clip, transform, out_path)
        ffmpeg = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
        if not ffmpeg:
            raise pa.PresentationError("ffmpeg not available")
        extra_loops = max(1, int(math.ceil(self.min_seconds / dur)) - 1)
        vf = (
            f"scale={transform.content_width}:{transform.content_height}:force_original_aspect_ratio=decrease,"
            f"pad={transform.target_width}:{transform.target_height}:{transform.pad_left}:{transform.pad_top}:black,"
            f"setsar=1"
        )
        cmd = build_loop_ffmpeg_argv(ffmpeg, src, out_path, extra_loops, vf)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out_path.is_file():
            raise pa.PresentationError(f"ffmpeg loop failed: {proc.stderr[-300:]}")
        self.looped = True
        return out_path.read_bytes()


# --------------------------------------------------------------------------- #
# Pipeline construction (no GPU / network at build time)
# --------------------------------------------------------------------------- #


class NvidiaSmiMetrics:
    """GpuMetricsProvider via nvidia-smi (a driver query, not GPU work). Only used when min free VRAM > 0."""

    def free_vram_mib(self) -> int:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True, timeout=20
        )
        return int(out.split()[0])


def settings_factory_for(cfg: ChapterVideoConfig) -> Callable[[str], i2v.I2VSettings]:
    def _factory(backend_id: str) -> i2v.I2VSettings:
        base = wiring.default_settings_for_backend(backend_id)
        if backend_id == reg.BACKEND_ID_WAN_22:
            return dataclasses.replace(
                base, frame_count=cfg.frames, fps=cfg.fps, min_free_vram_mib=cfg.min_free_vram_mib
            )
        return dataclasses.replace(base, min_free_vram_mib=cfg.min_free_vram_mib)

    return _factory


def build_backend_pipeline(
    cfg: ChapterVideoConfig,
    backend: str,
    store_root: "os.PathLike[str] | str",
    *,
    transport: Any = None,
    gpu_metrics: Any = None,
    gpu_lease: Any = None,
    render: Optional[Callable[..., bytes]] = None,
) -> MediaPipeline:
    """MediaPipeline for ONE backend. Transport is always real (never the adapter's FAKE dry-run bytes)."""
    root = Path(store_root) / backend
    if transport is None:
        models = WAN_22_REQUIRED_MODELS if backend == reg.BACKEND_ID_WAN_22 else SVD_REQUIRED_MODELS
        transport = ComfyHttpI2VTransport(cfg.comfy_url, max_wait_s=cfg.max_wait_s, required_models=models)
    if gpu_metrics is None and cfg.min_free_vram_mib > 0:
        gpu_metrics = NvidiaSmiMetrics()
    stage_image = None
    if backend == reg.BACKEND_ID_SVD_XT_1_1:
        # The adapter only auto-stages for wan_22; SVD needs the still uploaded to Comfy too.
        def stage_image(source_image: Any, transform: Any, job_id: str) -> str:  # type: ignore[misc]
            return transport.stage_and_upload(source_image, transform.target_width, transform.target_height, job_id)
    adapter = i2v.ImageToVideoAdapter(
        store=i2v.VideoJobStore(root / "i2v_jobs"),
        transport=transport,
        gpu_metrics=gpu_metrics,
        gpu_lease=gpu_lease,
        stage_image=stage_image,
    )
    return wiring.build_default_media_pipeline(
        root,
        transport=transport,
        gpu_metrics=gpu_metrics,
        gpu_lease=gpu_lease,
        i2v_adapter=adapter,
        render=render,
        environ={reg.ENV_I2V_BACKEND: backend},
        settings_factory=settings_factory_for(cfg),
        video_required=True,
        min_duration_seconds=cfg.min_seconds,
    )


# --------------------------------------------------------------------------- #
# Result + driver
# --------------------------------------------------------------------------- #


@dataclass
class ChapterClipResult:
    outcome: str  # SOCIAL_READY | MEDIA_HOLD
    hold_reason: Optional[str] = None
    asset_path: Optional[str] = None
    asset_sha256: Optional[str] = None
    backend_used: Optional[str] = None
    fallback_used: bool = False
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    frame_count: Optional[int] = None
    looped: bool = False
    workflow_id: Optional[str] = None
    source_image_path: Optional[str] = None
    source_image_sha256: Optional[str] = None
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    comfy: str = ""
    comfy_restarts: int = 0
    video_creates_identity_canon: bool = VIDEO_CREATES_IDENTITY_CANON
    wiring_version: str = WIRING_VERSION

    @property
    def ready(self) -> bool:
        return self.outcome == SOCIAL_READY and bool(self.asset_path)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _hold(reason: str, **kw: Any) -> ChapterClipResult:
    return ChapterClipResult(outcome=MEDIA_HOLD, hold_reason=f"VIDEO_REQUIRED_MISSING:{reason}", **kw)


PipelineBuilder = Callable[[str], MediaPipeline]


def produce_chapter_clip(
    still_path: "os.PathLike[str] | str",
    *,
    workflow_id: str,
    store_root: "os.PathLike[str] | str",
    still_approved: bool,
    cfg: Optional[ChapterVideoConfig] = None,
    seed: Optional[int] = None,
    source_character_intent: str = "INTENT_NO",
    pipeline_builder: Optional[PipelineBuilder] = None,
    comfy_runner: LauncherRunner = default_launcher_runner,
    skip_comfy_guard: bool = False,
    probe: Callable[[Path], Any] = probe_presented_video,
    queue_probe: QueueProbe = default_queue_probe,
    sleep: Callable[[float], Any] = time.sleep,
) -> ChapterClipResult:
    """Wan -> SVD -> MEDIA_HOLD for one approved still. Never raises; never returns a still/old clip."""
    cfg = cfg or ChapterVideoConfig.from_env()
    still = Path(still_path)
    base: Dict[str, Any] = {"workflow_id": workflow_id, "source_image_path": str(still)}
    if not cfg.enabled:
        return _hold("CHAPTER_VIDEO_BACKEND_OFF", **base)
    if cfg.problems:
        return _hold("CONFIG_INVALID:" + ";".join(cfg.problems), **base)
    if not still_approved:
        return _hold("STILL_NOT_APPROVED", **base)
    if not still.is_file():
        return _hold("SOURCE_STILL_MISSING", **base)
    try:
        sha = _sha256_file(still)
        from PIL import Image  # local import: keeps module import light

        with Image.open(still) as im:
            width, height = im.size
    except Exception as exc:  # noqa: BLE001
        return _hold(f"SOURCE_STILL_UNREADABLE:{type(exc).__name__}", **base)
    base["source_image_sha256"] = sha
    if seed is None:
        seed = int(sha[:8], 16)

    comfy = ComfyReady(True, reason="skipped")
    if not skip_comfy_guard:
        comfy = ensure_comfy_ready(cfg, comfy_runner, queue_probe, sleep)
        if not comfy.ok:
            return _hold(comfy.reason, comfy=comfy.reason, **base)
    attempts: List[Dict[str, Any]] = []
    restarts = 0
    abort = False

    def _attempt(backend: str, idx: int, wf: str) -> Tuple[Optional[ChapterClipResult], Dict[str, Any]]:
        loop_render = LoopingRender(cfg.min_seconds) if cfg.loop_fallback else None
        try:
            if pipeline_builder is not None:
                pipeline = pipeline_builder(backend)
            else:
                pipeline = build_backend_pipeline(cfg, backend, store_root, render=loop_render)
            res = pipeline.produce_social_media(
                ApprovedStillRef(
                    image_path=str(still),
                    source_image_sha256=sha,
                    image_source_approved=True,
                    source_character_intent=source_character_intent,
                    source_width=int(width),
                    source_height=int(height),
                ),
                workflow_id=wf,
                seed=int(seed),
            )
        except Exception as exc:  # noqa: BLE001 - one backend failing must not skip the fallback
            return None, {"backend": backend, "outcome": "ERROR", "reason": f"{type(exc).__name__}:{str(exc)[:200]}"}
        rd = res.to_dict()
        attempt: Dict[str, Any] = {"backend": backend, "outcome": rd.get("outcome"), "reason": rd.get("failure_reason")}
        asset = rd.get("asset_path")
        if rd.get("outcome") == SOCIAL_READY and asset and Path(asset).is_file():
            # Independent re-check of the final file (belt and braces on top of the pipeline gate).
            verdict = validate_presented_social_video(asset, min_duration=cfg.min_seconds)
            if verdict.ok:
                info = verdict.probe
                return ChapterClipResult(
                    outcome=SOCIAL_READY,
                    asset_path=str(asset),
                    asset_sha256=rd.get("asset_sha256") or _sha256_file(Path(asset)),
                    backend_used=backend,
                    fallback_used=idx > 0,
                    duration_seconds=round(float(getattr(info, "duration", 0.0) or 0.0), 3),
                    width=int(getattr(info, "width", 0) or 0),
                    height=int(getattr(info, "height", 0) or 0),
                    frame_count=int(getattr(info, "frame_count", 0) or 0),
                    looped=bool(loop_render.looped) if loop_render else False,
                    attempts=attempts,
                    comfy=comfy.reason,
                    comfy_restarts=restarts,
                    **base,
                ), attempt
            attempt["outcome"] = MEDIA_HOLD
            attempt["reason"] = verdict.failure_reason
        return None, attempt

    try:
        for idx, backend in enumerate(cfg.backend_order):
            retried = False
            while True:
                # frames/fps/min are part of the job identity (the adapter's idempotency key ignores them);
                # a post-crash retry gets its own key so a stale GENERATING record of the dead server is never reconciled.
                wf = f"{workflow_id}|{backend}|{cfg.frames}x{cfg.fps}|min{cfg.min_seconds:g}" + ("|retry1" if retried else "")
                clip, attempt = _attempt(backend, idx, wf)
                if retried:
                    attempt["retry"] = 1
                attempts.append(attempt)
                if clip is not None:
                    clip.comfy_restarts = restarts
                    return clip
                # Failed. Crash resilience: restart ONLY if the launcher says the port is free (ComfyUI is gone).
                if retried or restarts >= 1 or skip_comfy_guard:
                    break
                gone = restart_comfy_if_gone(cfg, comfy_runner)
                if gone.reason == COMFY_STILL_ALIVE:
                    attempt["comfy_alive"] = True  # alive but erroring: never restarted, go to the next backend
                    break
                if not gone.ok:
                    attempts.append({"backend": backend, "outcome": "COMFY_RESTART_FAILED", "reason": gone.reason})
                    abort = True  # ComfyUI is gone and could not be brought back: fail closed
                    break
                restarts += 1
                comfy = ComfyReady(True, started_by_us=True, reason=gone.reason)
                attempts.append({"backend": backend, "outcome": "COMFY_RESTARTED", "reason": gone.reason})
                retried = True
            if abort:
                break
        reasons = "|".join(
            f"{a['backend']}:{a.get('reason') or a.get('outcome')}" for a in attempts if a.get("outcome") != "COMFY_RESTARTED"
        ) or "no_backend_attempted"
        return _hold(reasons, attempts=attempts, comfy=comfy.reason, comfy_restarts=restarts, **base)
    finally:
        if comfy.started_by_us and cfg.stop_comfy_after:
            stop_comfy_started_by_us(cfg, comfy_runner)


# --------------------------------------------------------------------------- #
# Verification used by the quality gate (CPU / ffprobe only)
# --------------------------------------------------------------------------- #


def verify_motion_clip(
    video_path: "os.PathLike[str] | str",
    clip_meta: Optional[Mapping[str, Any]],
    *,
    min_seconds: float = MIN_SOCIAL_VIDEO_SECONDS,
) -> Tuple[bool, str]:
    """True only if the file is exactly the clip this wiring produced (sha) and still meets the media gate."""
    p = Path(video_path)
    if not p.is_file():
        return False, "video_missing"
    if not clip_meta or not clip_meta.get("asset_sha256"):
        return False, "not_produced_by_chapter_video_wiring"
    if _sha256_file(p) != str(clip_meta.get("asset_sha256")):
        return False, "sha256_mismatch_stale_or_replaced_clip"
    verdict = validate_presented_social_video(p, min_duration=max(float(min_seconds), MIN_SOCIAL_VIDEO_SECONDS))
    if not verdict.ok:
        return False, str(verdict.failure_reason)
    return True, "ok"