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
CHAPTER_VIDEO_STEP_TIMEOUT_S (3600, floored at 60: overall deadline on the whole clip step -> MEDIA_HOLD),
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
  * that retry crashed ComfyUI again (e.g. access violation in the final VAE decode) -> before the
    SVD fallback, ONE more fresh start via the launcher (``-Status`` dynvram_disabled=True required),
    only when the server is confirmed dead (port free) or this run owns it and it no longer answers
    ``/queue`` (launcher ``-Stop`` of our own pid first). A live / foreign / busy instance is never
    stopped. Start failure, or no time left under CHAPTER_VIDEO_STEP_TIMEOUT_S -> MEDIA_HOLD. The result
    records it in ``fallback_restart`` (``svd_after_restart`` / ``svd_restart_failed:...``).
  * step deadline hit -> the caller gets MEDIA_HOLD at once and a cancel Event is set; from then on the
    abandoned worker never calls the launcher (no -Status/-Stop/start, no crash restart, no pre-SVD
    restart) and never submits another job to ComfyUI.
Every subprocess here is built as an argv LIST (no shell=True, no joined command strings), so paths
with spaces (e.g. a repo folder called 'Automation tool') are safe. The launcher runs with NO pipes
(stdin DEVNULL, output to a temp file): the ComfyUI it starts inherits handles, and an inherited pipe
used to block ``subprocess.run`` forever on Windows. A launcher timeout kills the launcher tree -> MEDIA_HOLD.

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
from tools import video_frame_probe as vfp
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
ENV_STEP_TIMEOUT = "CHAPTER_VIDEO_STEP_TIMEOUT_S"

BACKEND_OFF = "off"
DEFAULT_BACKEND = reg.BACKEND_ID_WAN_22
DEFAULT_FRAMES = 73  # 4n+1; 73 / 24 fps = 3.04 s
DEFAULT_FPS = 24
DEFAULT_LAUNCHER = r"C:\Users\David\ComfyUI-Launch\start_comfyui_wan.bat"
DEFAULT_STEP_TIMEOUT_S = 3600.0  # whole clip step (start + Wan + SVD fallback); never wait longer
MIN_STEP_TIMEOUT_S = 60.0
SVD_REQUIRED_MODELS: Dict[str, str] = {"svd_xt_1_1.safetensors": "checkpoints"}

MEDIA_HOLD = PipelineOutcome.MEDIA_HOLD.value
SOCIAL_READY = PipelineOutcome.SOCIAL_READY.value
# An SVD-only clip (Wan failed, SVD succeeded; or SVD chosen) is never SOCIAL_READY: the result is MEDIA_HOLD with
# this reason, so the Reel/Short (social/video) post waits. It holds the social side only: the Patreon / Royal Road
# text release never reads the Reel pack or its clip. The clip file is kept (asset_path) for review; what it is
# (backend, fps, fallback_restart, ...) is in ``clip_metadata`` and on the successful attempt record (``clip``).
# Wan results stay SOCIAL_READY.
SVD_FALLBACK_SOCIAL_HOLD = "SVD_FALLBACK_SOCIAL_HOLD"
SOCIAL_HOLD_BACKENDS = frozenset({reg.BACKEND_ID_SVD_XT_1_1})

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
    step_timeout_s: float = DEFAULT_STEP_TIMEOUT_S
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
            step_timeout_s=max(MIN_STEP_TIMEOUT_S, _env_float(env, ENV_STEP_TIMEOUT, DEFAULT_STEP_TIMEOUT_S, problems)),
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


def _kill_process_tree(proc: "subprocess.Popen[Any]") -> None:
    """Kill ``proc`` and every descendant (Windows: ``taskkill /T /F``; POSIX: its process group)."""
    if proc.poll() is not None and os.name != "nt":
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=30, check=False,
            )
        else:
            import signal

            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        pass


def default_launcher_runner(args: Sequence[str], timeout: float) -> Tuple[int, str]:
    """Run the launcher (argv LIST, never shell=True) with NO pipes.

    The launcher's background start (``Start-Process``) hands its inherited handles to the fresh ComfyUI.
    With ``capture_output=True`` that child kept the stdout/stderr PIPE open and ``subprocess.run`` waited on
    it forever on Windows, even past ``timeout`` (the 24 h hang). Output now goes to an anonymous temp FILE
    (a child holding a file handle blocks nothing) and stdin is DEVNULL. The timeout is enforced on the
    launcher process itself; on expiry the whole launcher tree is killed and ``subprocess.TimeoutExpired``
    is raised, which every caller turns into a not-ok ComfyReady -> MEDIA_HOLD.
    """
    import tempfile

    popen_kw: Dict[str, Any] = {}
    if os.name == "nt":
        popen_kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kw["start_new_session"] = True
    with tempfile.TemporaryFile() as out_f:
        proc = subprocess.Popen(
            list(args), stdin=subprocess.DEVNULL, stdout=out_f, stderr=subprocess.STDOUT, **popen_kw
        )
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            raise
        except BaseException:
            _kill_process_tree(proc)
            raise
        out_f.seek(0)
        text = out_f.read().decode("utf-8", "replace")
    return rc, text


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


START_TIMEOUT_S = 480.0
STATUS_TIMEOUT_S = 90.0


def start_comfy_via_launcher(
    cfg: ChapterVideoConfig, runner: LauncherRunner = default_launcher_runner, start_timeout: float = START_TIMEOUT_S
) -> ComfyReady:
    """Start exactly ONE ComfyUI through the launcher .bat (caller has confirmed the port is free), then
    require ``-Status`` dynvram_disabled=True. Never starts anything but via the launcher."""
    bat = cfg.comfy_launcher
    try:
        rc, out = runner(launcher_argv(bat), float(start_timeout))
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
    cfg: ChapterVideoConfig,
    runner: LauncherRunner = default_launcher_runner,
    on_starting: Optional[Callable[[], Any]] = None,
) -> ComfyReady:
    """After a failed attempt: if (and only if) the launcher reports the port FREE (ComfyUI died / crashed),
    start a fresh instance via the launcher. A still-alive instance is never touched."""
    st, err = _launcher_status(cfg, runner)
    if st is None:
        return ComfyReady(False, reason=err)
    if st.port_busy:
        return ComfyReady(False, reason=COMFY_STILL_ALIVE)
    if on_starting is not None:
        on_starting()  # lets the step deadline -Stop a half-started instance of ours
    res = start_comfy_via_launcher(cfg, runner)
    if res.ok:
        res.reason = "restarted_after_crash_via_launcher"
    return res


COMFY_STILL_ALIVE = "COMFY_STILL_ALIVE_NOT_RESTARTED"
CLIP_STEP_CANCELLED = "CLIP_STEP_CANCELLED"


class ClipStepCancelled(RuntimeError):
    """Raised instead of running the launcher once the step deadline cancelled this clip step."""

FALLBACK_RESTART_OK = "svd_after_restart"
FALLBACK_RESTART_FAILED = "svd_restart_failed"
FALLBACK_NOT_NEEDED = "COMFY_ALIVE_NO_RESTART_NEEDED"
MIN_RESTART_BUDGET_S = 30.0  # less than this left under the step deadline -> do not even try a start


def restart_comfy_before_fallback(
    cfg: ChapterVideoConfig,
    runner: LauncherRunner = default_launcher_runner,
    queue_probe: QueueProbe = default_queue_probe,
    sleep: Callable[[float], Any] = time.sleep,
    *,
    owned: bool,
    remaining_s: Optional[Callable[[], float]] = None,
    on_starting: Optional[Callable[[], Any]] = None,
) -> ComfyReady:
    """The Wan retry is used up and the fallback backend needs a ComfyUI: one fresh start via the launcher.

    * port FREE (server confirmed dead)                  -> start via the launcher.
    * port busy, this run owns it, ``/queue`` unanswered  -> launcher ``-Stop`` (own pid only), port free, start.
    * port busy and ``/queue`` answers (alive, ours or not) -> ``FALLBACK_NOT_NEEDED`` (never restarted).
    * port busy, not ours, ``/queue`` unanswered          -> not-ok: someone else's instance is never stopped.
    The start always ends with ``-Status`` dynvram_disabled=True (start_comfy_via_launcher). Every launcher
    timeout is capped by ``remaining_s()`` (time left under the step deadline).
    """
    def _budget(cap: float) -> Optional[float]:
        if remaining_s is None:
            return cap
        left = float(remaining_s())
        if left < MIN_RESTART_BUDGET_S:
            return None
        return max(1.0, min(cap, left - 5.0))

    if _budget(STATUS_TIMEOUT_S) is None:
        return ComfyReady(False, reason="COMFY_FALLBACK_RESTART_NO_TIME_LEFT")
    st, err = _launcher_status(cfg, runner)
    if st is None:
        return ComfyReady(False, reason=err or "COMFY_STATUS_UNUSABLE")
    if st.port_busy:
        try:
            queue = queue_probe(cfg.comfy_url, 8.0)
        except Exception:  # noqa: BLE001
            queue = None
        if queue is not None:
            return ComfyReady(True, started_by_us=owned, reason=FALLBACK_NOT_NEEDED)
        if not owned:
            return ComfyReady(False, reason="COMFY_FOREIGN_INSTANCE_UNRESPONSIVE_NOT_STOPPED")
        try:
            stop_rc, _out = runner(launcher_argv(cfg.comfy_launcher, "-Stop"), STATUS_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001
            return ComfyReady(False, reason=f"COMFY_STOP_ERROR:{type(exc).__name__}:{str(exc)[:120]}")
        if stop_rc != 0:
            return ComfyReady(False, reason=f"COMFY_OWN_INSTANCE_NOT_STOPPABLE_BY_LAUNCHER:rc={stop_rc}")
        free = _wait_port_free(cfg, runner, sleep)
        if free is not True:
            return ComfyReady(False, reason="COMFY_FALLBACK_RESTART_PORT_STILL_BUSY" if free is False else "COMFY_STATUS_UNUSABLE_AFTER_STOP")
    budget = _budget(START_TIMEOUT_S)
    if budget is None:
        return ComfyReady(False, reason="COMFY_FALLBACK_RESTART_NO_TIME_LEFT")
    if on_starting is not None:
        on_starting()  # lets the step deadline -Stop a half-started instance of ours
    res = start_comfy_via_launcher(cfg, runner, start_timeout=budget)
    if res.ok:
        res.reason = "restarted_before_fallback_via_launcher"
    return res


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
    """argv LIST for the opt-in loop render (paths with spaces stay single elements); stop on decode error, single-threaded."""
    return [str(ffmpeg), "-y", "-hide_banner", "-nostdin", *vfp.FFMPEG_SAFE_INPUT_ARGS,
            "-stream_loop", str(int(extra_loops)), "-i", str(src), "-vf", vf,
            "-threads", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out_path)]


class LoopingRender:
    """RenderFn: default FIT_INSIDE ffmpeg render, but loop a too-short source up to ``min_seconds``."""

    def __init__(self, min_seconds: float, probe: Callable[[Path], Any] = probe_presented_video) -> None:
        self.min_seconds = float(min_seconds)
        self._probe = probe
        self.looped = False

    def __call__(self, clip: Any, transform: Any, out_path: Path, *, timeout_s: Optional[float] = None) -> bytes:
        src = Path(clip.video_path)
        info = self._probe(src)
        dur = float(getattr(info, "duration", 0.0) or 0.0)
        if dur <= 0:
            raise pa.PresentationError("loop render: source duration unknown")
        if dur + 1e-6 >= self.min_seconds:
            return pa.default_ffmpeg_render(clip, transform, out_path, timeout_s=timeout_s)
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
        data = pa.run_presentation_ffmpeg(cmd, out_path, label="ffmpeg loop", timeout_s=timeout_s)
        self.looped = True
        return data


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
    fallback_restart: str = ""  # "" | svd_after_restart | svd_restart_failed:<reason>
    social_hold: bool = False  # True: a verified clip exists but is held for social (SVD_FALLBACK_SOCIAL_HOLD)
    clip_metadata: Dict[str, Any] = field(default_factory=dict)  # backend / fps / fallback_restart / sizes
    presentation_retry: str = ""  # "" | recovered | failed | skipped:<why> (presentation-only retry from the saved raw clip)
    frame_probe: Dict[str, Any] = field(default_factory=dict)  # ffprobe -count_frames of the raw and presented mp4
    video_creates_identity_canon: bool = VIDEO_CREATES_IDENTITY_CANON
    wiring_version: str = WIRING_VERSION

    @property
    def ready(self) -> bool:
        return self.outcome == SOCIAL_READY and bool(self.asset_path)

    @property
    def clip_produced(self) -> bool:
        """A verified clip file exists: SOCIAL_READY, or an SVD clip held for social."""
        return bool(self.asset_path) and (self.outcome == SOCIAL_READY or self.social_hold)

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


def _raw_generation_settings(cfg: ChapterVideoConfig, backend: Optional[str]) -> Dict[str, Any]:
    """What the backend generated before presentation (SVD: 25 frames @ 6 fps, 1024x576)."""
    try:
        st = settings_factory_for(cfg)(str(backend or ""))
        return {
            "raw_frame_count": int(st.frame_count),
            "raw_fps": st.fps,
            "raw_width": int(st.target_width),
            "raw_height": int(st.target_height),
        }
    except Exception as exc:  # noqa: BLE001 - metadata must never fail the clip step
        return {"raw_settings_error": f"{type(exc).__name__}:{str(exc)[:120]}"}


def clip_result_metadata(cfg: ChapterVideoConfig, clip: ChapterClipResult) -> Dict[str, Any]:
    """What the clip is, for Product Performance / Social: backend, fps, fallback_restart, raw and output sizes."""
    frames = int(clip.frame_count or 0)
    duration = float(clip.duration_seconds or 0.0)
    raw = _raw_generation_settings(cfg, clip.backend_used)
    probed_raw = (clip.frame_probe or {}).get("raw") or {}
    probed_out = (clip.frame_probe or {}).get("presented") or {}
    if probed_raw.get("frames") is not None:
        # Record what the file really holds (ffprobe -count_frames), not what was requested.
        raw["raw_frame_count_requested"] = raw.get("raw_frame_count")
        raw["raw_frame_count"] = int(probed_raw["frames"])
        raw["raw_frame_count_source"] = "ffprobe"
        raw["raw_pts_missing"] = list(probed_raw.get("missing_indices") or [])
    else:
        raw["raw_frame_count_source"] = "requested"
    extra: Dict[str, Any] = {"presentation_retry": clip.presentation_retry}
    if probed_out:
        extra["output_pts_missing"] = list(probed_out.get("missing_indices") or [])
    return {
        "backend": clip.backend_used,
        "fps": raw.get("raw_fps"),
        "fallback_used": bool(clip.fallback_used),
        "fallback_restart": clip.fallback_restart,
        **raw,
        "output_width": clip.width,
        "output_height": clip.height,
        "output_frame_count": frames,
        "output_fps": round(frames / duration, 3) if frames > 0 and duration > 0 else None,
        "duration_seconds": clip.duration_seconds,
        "looped": bool(clip.looped),
        "social_status": clip.outcome,
        "social_hold": bool(clip.social_hold),
        "hold_reason": clip.hold_reason or "",
        **extra,
    }


def finalize_clip_result(cfg: ChapterVideoConfig, clip: ChapterClipResult,
                         attempt: Optional[Dict[str, Any]] = None) -> ChapterClipResult:
    """SVD clips -> MEDIA_HOLD (SVD_FALLBACK_SOCIAL_HOLD), Wan unchanged; record clip metadata on result + attempt."""
    if clip.outcome == SOCIAL_READY and clip.backend_used in SOCIAL_HOLD_BACKENDS:
        clip.outcome = MEDIA_HOLD
        clip.hold_reason = SVD_FALLBACK_SOCIAL_HOLD
        clip.social_hold = True
    clip.clip_metadata = clip_result_metadata(cfg, clip)
    if attempt is not None:
        attempt["clip"] = dict(clip.clip_metadata, asset_path=clip.asset_path, asset_sha256=clip.asset_sha256)
    return clip


PRESENTATION_MIN_BUDGET_S = 30.0  # never start a presentation encode with less than this left before the step deadline


class PresentationGuard:
    """RenderFn for one backend attempt (presentation stage only).

    * honours the step cancel flag and deadline before every ffmpeg run, and bounds ffmpeg by the time left;
    * probes the raw clip once (ffprobe -count_frames): exactly ``expected`` frames, contiguous pts -- otherwise
      the raw clip is rejected (a backend failure; no presentation retry);
    * probes the presented mp4 the same way (unless the opt-in loop render looped it);
    * ``retry_allowed`` gates MediaPipeline's single presentation-only retry: raw verified, not cancelled, time left.
    """

    def __init__(self, expected_frames: int, *, cancelled: Callable[[], bool], remaining: Callable[[], float],
                 base_render: Optional[Callable[..., bytes]] = None) -> None:
        self.expected = int(expected_frames or 0)
        self._cancelled = cancelled
        self._remaining = remaining
        self._base = base_render
        self.probes: Dict[str, Any] = {}
        self.raw_ok: Optional[bool] = None
        self.renders = 0

    def _budget_problem(self) -> str:
        if self._cancelled():
            return "cancelled"
        if self._remaining() < PRESENTATION_MIN_BUDGET_S:
            return "no_time_left"
        return ""

    def retry_allowed(self) -> Any:
        if self.raw_ok is not True:
            return "raw_clip_not_verified"
        return self._budget_problem() or True

    def __call__(self, clip: Any, transform: Any, out_path: Path) -> bytes:
        problem = self._budget_problem()
        if problem:
            tag = CLIP_STEP_CANCELLED if problem == "cancelled" else CLIP_STEP_TIMEOUT
            raise pa.PresentationError(f"{tag}:presentation_not_started:{problem}")
        if self.raw_ok is None:
            raw = vfp.probe_frames(clip.video_path)
            self.probes["raw"] = raw.to_dict()
            bad = vfp.frame_check_failure(raw, self.expected) if self.expected else None
            self.raw_ok = bad is None
            if bad:
                raise pa.PresentationError(f"RAW_CLIP_REJECTED:{bad}")
        elif self.raw_ok is False:
            raise pa.PresentationError("RAW_CLIP_REJECTED")
        self.renders += 1
        left = self._remaining()
        base = self._base or pa.default_ffmpeg_render
        data = base(clip, transform, out_path, timeout_s=None if math.isinf(left) else left)
        out = vfp.probe_frames(out_path)
        self.probes["presented"] = out.to_dict()
        if self.expected and not bool(getattr(base, "looped", False)):
            bad = vfp.frame_check_failure(out, self.expected)
            if bad:
                raise pa.PresentationError(f"PRESENTED_CLIP_REJECTED:{bad}")
        return data


PipelineBuilder = Callable[[str], MediaPipeline]


def _produce_chapter_clip_inner(
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
    _state: Optional[Dict[str, Any]] = None,
) -> ChapterClipResult:
    """The clip step itself (no deadline); ``produce_chapter_clip`` runs it under the overall deadline."""
    _state = {} if _state is None else _state
    cfg = cfg or ChapterVideoConfig.from_env()
    cancel = _state.get("cancel")

    def _cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    raw_runner = comfy_runner

    def comfy_runner(args: Sequence[str], timeout: float) -> Tuple[int, str]:  # noqa: F811 - guarded launcher
        # Once the step deadline fired, the abandoned worker must never run the launcher again
        # (no start, no -Status/-Stop, no restart). Every caller already turns an exception into not-ok.
        if _cancelled():
            raise ClipStepCancelled(f"{CLIP_STEP_CANCELLED}:launcher_call_blocked")
        return raw_runner(args, timeout)
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
    if _cancelled():
        return _hold(CLIP_STEP_CANCELLED, **base)
    if not skip_comfy_guard:
        comfy = ensure_comfy_ready(cfg, comfy_runner, queue_probe, sleep)
        _state["comfy"] = comfy
        if not comfy.ok:
            return _hold(comfy.reason, comfy=comfy.reason, **base)
    attempts: List[Dict[str, Any]] = []
    restarts = 0
    abort = False
    comfy_maybe_down = False  # the Wan retry was used up after a crash restart
    fallback_restart = ""
    deadline = _state.get("deadline")

    def _remaining() -> float:
        return float("inf") if deadline is None else float(deadline) - time.monotonic()

    def _attempt(backend: str, idx: int, wf: str) -> Tuple[Optional[ChapterClipResult], Dict[str, Any]]:
        loop_render = LoopingRender(cfg.min_seconds) if cfg.loop_fallback else None
        guard = PresentationGuard(
            int(_raw_generation_settings(cfg, backend).get("raw_frame_count") or 0),
            cancelled=_cancelled, remaining=_remaining, base_render=loop_render)
        if _cancelled():  # never submit to ComfyUI after the deadline
            return None, {"backend": backend, "outcome": CLIP_STEP_CANCELLED, "reason": "not_submitted_after_step_timeout"}
        try:
            if pipeline_builder is not None:
                pipeline = pipeline_builder(backend)
            else:
                pipeline = build_backend_pipeline(cfg, backend, store_root, render=guard)
                if isinstance(pipeline, MediaPipeline):
                    # Only the presentation encode failed and the raw clip passed: ONE re-run from the saved raw clip
                    # (no new render, no ComfyUI restart), inside the step deadline and the cancel flag.
                    pipeline.presentation_retries = 1
                    pipeline.presentation_retry_allowed = guard.retry_allowed
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
        if rd.get("presentation_retry"):
            attempt["presentation_retry"] = rd.get("presentation_retry")
        if guard.probes:
            attempt["frame_probe"] = dict(guard.probes)
        asset = rd.get("asset_path")
        if rd.get("outcome") == SOCIAL_READY and asset and Path(asset).is_file():
            # Independent re-check of the final file (belt and braces on top of the pipeline gate).
            verdict = validate_presented_social_video(asset, min_duration=cfg.min_seconds)
            looped = bool(loop_render.looped) if loop_render else False
            if verdict.ok and guard.renders and guard.expected and not looped \
                    and int(getattr(verdict.probe, "frame_count", 0) or 0) != guard.expected:
                attempt["outcome"] = MEDIA_HOLD
                attempt["reason"] = (f"PRESENTED_FRAME_COUNT_MISMATCH:probed={getattr(verdict.probe, 'frame_count', 0)},"
                                     f"expected={guard.expected}")
                return None, attempt
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
                    looped=looped,
                    presentation_retry=str(rd.get("presentation_retry") or ""),
                    frame_probe=dict(guard.probes),
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
            if _cancelled():
                attempts.append({"backend": backend, "outcome": CLIP_STEP_CANCELLED, "reason": "not_started_after_step_timeout"})
                break
            if idx > 0 and comfy_maybe_down and not skip_comfy_guard:
                comfy_maybe_down = False
                if _cancelled():
                    attempts.append({"backend": backend, "outcome": CLIP_STEP_CANCELLED, "reason": "no_restart_after_step_timeout"})
                    break

                def _starting() -> None:
                    _state["comfy"] = ComfyReady(False, started_by_us=True, reason="starting_before_fallback")

                again = restart_comfy_before_fallback(
                    cfg, comfy_runner, queue_probe, sleep, owned=bool(comfy.started_by_us),
                    remaining_s=_remaining if deadline is not None else None, on_starting=_starting)
                if again.reason == FALLBACK_NOT_NEEDED:
                    _state["comfy"] = comfy
                elif not again.ok:
                    fallback_restart = f"{FALLBACK_RESTART_FAILED}:{again.reason}"
                    attempts.append({"backend": backend, "outcome": "COMFY_RESTART_FAILED", "reason": again.reason,
                                     "stage": "before_fallback"})
                    # a half-started instance of ours was already stopped by start_comfy_via_launcher
                    comfy = ComfyReady(False, started_by_us=False, reason=again.reason)
                    _state["comfy"] = comfy
                    break  # ComfyUI is gone and could not be brought back: fail closed (MEDIA_HOLD)
                else:
                    restarts += 1
                    comfy = ComfyReady(True, started_by_us=True, reason=again.reason)
                    _state["comfy"] = comfy
                    fallback_restart = FALLBACK_RESTART_OK
                    attempts.append({"backend": backend, "outcome": "COMFY_RESTARTED", "reason": again.reason,
                                     "stage": "before_fallback", "status": FALLBACK_RESTART_OK})
            while True:
                # frames/fps/min are part of the job identity (the adapter's idempotency key ignores them);
                # a post-crash retry gets its own key so a stale GENERATING record of the dead server is never reconciled.
                wf = f"{workflow_id}|{backend}|{cfg.frames}x{cfg.fps}|min{cfg.min_seconds:g}" + ("|retry1" if retried else "")
                clip, attempt = _attempt(backend, idx, wf)
                if attempt.get("outcome") == CLIP_STEP_CANCELLED:
                    attempts.append(attempt)
                    abort = True
                    break
                if retried:
                    attempt["retry"] = 1
                attempts.append(attempt)
                if clip is not None:
                    clip.comfy_restarts = restarts
                    clip.fallback_restart = fallback_restart
                    return finalize_clip_result(cfg, clip, attempt)  # SVD -> held for social; Wan unchanged
                # Failed. Crash resilience: restart ONLY if the launcher says the port is free (ComfyUI is gone).
                if retried or restarts >= 1 or skip_comfy_guard:
                    if retried and not skip_comfy_guard:
                        comfy_maybe_down = True  # the fallback backend re-checks (and may restart) before it runs
                    break
                if _cancelled():  # deadline passed: no crash restart, no retry
                    attempts.append({"backend": backend, "outcome": CLIP_STEP_CANCELLED, "reason": "no_restart_after_step_timeout"})
                    abort = True
                    break
                gone = restart_comfy_if_gone(
                    cfg, comfy_runner,
                    on_starting=lambda: _state.__setitem__("comfy", ComfyReady(False, started_by_us=True, reason="starting_after_crash")))
                if gone.reason == COMFY_STILL_ALIVE:
                    attempt["comfy_alive"] = True  # alive but erroring: never restarted, go to the next backend
                    break
                if not gone.ok:
                    _state["comfy"] = comfy  # start_comfy_via_launcher already stopped a half-started instance of ours
                    attempts.append({"backend": backend, "outcome": "COMFY_RESTART_FAILED", "reason": gone.reason})
                    abort = True  # ComfyUI is gone and could not be brought back: fail closed
                    break
                restarts += 1
                comfy = ComfyReady(True, started_by_us=True, reason=gone.reason)
                _state["comfy"] = comfy
                attempts.append({"backend": backend, "outcome": "COMFY_RESTARTED", "reason": gone.reason})
                retried = True
            if abort:
                break
        reasons = "|".join(
            f"{a['backend']}:{a.get('reason') or a.get('outcome')}" for a in attempts if a.get("outcome") != "COMFY_RESTARTED"
        ) or "no_backend_attempted"
        return _hold(reasons, attempts=attempts, comfy=comfy.reason, comfy_restarts=restarts,
                     fallback_restart=fallback_restart, **base)
    finally:
        if comfy.started_by_us and cfg.stop_comfy_after:
            stop_comfy_started_by_us(cfg, comfy_runner)


CLIP_STEP_TIMEOUT = "CLIP_STEP_TIMEOUT"


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
    step_timeout_s: Optional[float] = None,
) -> ChapterClipResult:
    """Wan -> SVD -> MEDIA_HOLD for one approved still. Never raises; never returns a still/old clip.

    The whole clip step runs under one overall deadline (``CHAPTER_VIDEO_STEP_TIMEOUT_S``, default
    3600 s, floored at 1 s; ``step_timeout_s`` overrides it). Past the deadline the caller gets MEDIA_HOLD
    (``CLIP_STEP_TIMEOUT``) instead of waiting; a ComfyUI this run started is stopped through the launcher
    so the abandoned worker unblocks. The worker thread is a daemon and can never publish anything: its
    late result is discarded.
    """
    import threading

    cfg = cfg or ChapterVideoConfig.from_env()
    limit = float(step_timeout_s) if step_timeout_s is not None else float(cfg.step_timeout_s)
    limit = max(1.0, limit)
    cancel = threading.Event()
    state: Dict[str, Any] = {"comfy": None, "result": None, "error": None, "timed_out": False,
                             "deadline": time.monotonic() + limit, "cancel": cancel}

    def _run() -> None:
        try:
            state["result"] = _produce_chapter_clip_inner(
                still_path,
                workflow_id=workflow_id,
                store_root=store_root,
                still_approved=still_approved,
                cfg=cfg,
                seed=seed,
                source_character_intent=source_character_intent,
                pipeline_builder=pipeline_builder,
                comfy_runner=comfy_runner,
                skip_comfy_guard=skip_comfy_guard,
                probe=probe,
                queue_probe=queue_probe,
                sleep=sleep,
                _state=state,
            )
        except BaseException as exc:  # noqa: BLE001 - never raises to the caller
            state["error"] = exc

    worker = threading.Thread(target=_run, name=f"chapter-clip-{workflow_id}"[:60], daemon=True)
    worker.start()
    worker.join(limit)
    base: Dict[str, Any] = {"workflow_id": workflow_id, "source_image_path": str(Path(still_path))}
    if worker.is_alive():
        cancel.set()  # first: the abandoned worker may not restart / start / submit anything from here on
        state["timed_out"] = True
        comfy = state.get("comfy")
        if comfy is not None and getattr(comfy, "started_by_us", False) and cfg.stop_comfy_after:
            stop_comfy_started_by_us(cfg, comfy_runner)
        return _hold(f"{CLIP_STEP_TIMEOUT}:{limit:g}s", comfy=getattr(comfy, "reason", "") or "", **base)
    if state["error"] is not None:
        exc = state["error"]
        return _hold(f"UNEXPECTED_ERROR:{type(exc).__name__}:{str(exc)[:160]}", **base)
    return state["result"]


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