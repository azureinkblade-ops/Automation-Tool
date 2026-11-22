"""Exact frame-count checks for encoded clips, and the safe ffmpeg flags shared by every encode step.

Evidence (Research png-app-20261121-174605 + CPU repro, 2026-11-21): on this host ffmpeg intermittently
(a) crashes with 0xC0000005 mid-encode and (b) drops a PNG on a zlib "inflate returned error -3" while still
exiting 0, leaving a 72-frame mp4 with a pts hole. PIL decodes the same files cleanly every time. Multithreaded
decode/encode reproduced both (8 failures in 31 runs); single-threaded runs were clean (0 in 16).

So every ffmpeg step here:
  * stops on the first decode error (-xerror, -err_detect explode) instead of silently dropping a frame,
  * runs single-threaded (-threads 1 for the decoder and the encoder; 73 frames take ~2-4 s),
  * and its output is re-probed with ffprobe -count_frames: exactly the expected frames, contiguous pts.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, List, Optional, Union

# Before -i: stop on a decode error (no silent frame drop), single-threaded decode.
FFMPEG_SAFE_INPUT_ARGS: List[str] = ["-xerror", "-err_detect", "explode", "-threads", "1"]
# Output side: single-threaded encoder; keep source timestamps (a hole stays visible, never papered over).
FFMPEG_SAFE_OUTPUT_ARGS: List[str] = ["-fps_mode", "passthrough", "-threads", "1"]
STDERR_TAIL_CHARS = 2000
FRAME_PROBE_TIMEOUT_S = 120.0


def stderr_tail(text: Union[str, bytes, None], n: int = STDERR_TAIL_CHARS) -> str:
    """Last ``n`` chars of an ffmpeg log (the error is at the end, the banner at the start)."""
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return text[-n:]


def resolve_ffprobe(ffmpeg: Optional[str] = None) -> Optional[str]:
    """FFPROBE_PATH, else the ffprobe next to the ffmpeg in use (FFMPEG_PATH / PATH), else PATH."""
    env = os.environ.get("FFPROBE_PATH")
    if env:
        return env
    ff = ffmpeg or os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
    if ff:
        base = os.path.basename(ff).lower()
        name = "ffprobe.exe" if base.endswith(".exe") else "ffprobe"
        cand = os.path.join(os.path.dirname(ff), name)
        if os.path.isfile(cand):
            return cand
    return shutil.which("ffprobe")


@dataclass
class FrameProbe:
    path: str
    frames: Optional[int] = None  # nb_read_frames (decoded), not the container's claim
    packets: int = 0
    missing_indices: List[int] = field(default_factory=list)  # pts holes, as frame indices
    error: str = ""

    @property
    def contiguous(self) -> bool:
        return not self.error and not self.missing_indices and self.frames == self.packets

    def to_dict(self) -> dict:
        d = asdict(self)
        d["contiguous"] = self.contiguous
        return d


def probe_frames(path: "os.PathLike[str] | str", *, ffprobe: Optional[str] = None,
                 run: Callable[..., Any] = subprocess.run, timeout: float = FRAME_PROBE_TIMEOUT_S) -> FrameProbe:
    """ffprobe -count_frames + packet pts of the first video stream. Never raises; problems go to ``error``."""
    out = FrameProbe(path=str(path))
    exe = ffprobe or resolve_ffprobe()
    if not exe:
        out.error = "ffprobe_unavailable"
        return out
    argv = [str(exe), "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=nb_read_frames:packet=pts", "-of", "json", str(path)]
    try:
        proc = run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        out.error = f"ffprobe_timeout_{timeout:g}s"
        return out
    except OSError as exc:
        out.error = f"ffprobe_not_started:{exc}"
        return out
    if getattr(proc, "returncode", 1) != 0:
        out.error = f"ffprobe_rc={proc.returncode}:{stderr_tail(proc.stderr, 300)}"
        return out
    try:
        data = json.loads(stderr_tail(proc.stdout, 10 ** 9) or "{}")
        streams = data.get("streams") or []
        if not streams:
            out.error = "no_video_stream"
            return out
        out.frames = int(str(streams[0].get("nb_read_frames") or "0").strip() or 0)
        pts = sorted(int(p["pts"]) for p in (data.get("packets") or []) if str(p.get("pts", "")).lstrip("-").isdigit())
    except (ValueError, TypeError, KeyError) as exc:
        out.error = f"ffprobe_parse:{exc}"
        return out
    out.packets = len(pts)
    deltas = [b - a for a, b in zip(pts, pts[1:]) if b > a]
    if deltas:
        step = min(deltas)
        idx = sorted({(p - pts[0]) // step for p in pts})
        out.missing_indices = sorted(set(range(idx[-1] + 1)) - set(idx))
    return out


def frame_check_failure(probe: FrameProbe, expected: int) -> Optional[str]:
    """None when the clip has exactly ``expected`` decodable frames with contiguous pts; else the reason."""
    if probe.error:
        return f"FRAME_PROBE_FAILED:{probe.error}"
    if probe.frames != int(expected):
        return f"FRAME_COUNT_MISMATCH:probed={probe.frames},expected={int(expected)}"
    if probe.missing_indices:
        return f"FRAME_PTS_GAP:missing_idx={probe.missing_indices[:10]}"
    if probe.packets != probe.frames:
        return f"FRAME_PACKET_MISMATCH:packets={probe.packets},frames={probe.frames}"
    return None
