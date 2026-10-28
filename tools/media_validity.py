"""Media validity gates before SOCIAL_READY.

Reject tiny/undecodable/zero-duration/wrong-dimension presented videos.
On failure callers should fall back to STATIC_FALLBACK (publication not blocked on video).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from tools.i2v_presentation_adapter import DEFAULT_SOCIAL_HEIGHT, DEFAULT_SOCIAL_WIDTH


# Soft 158B presented mp4 was observed; floor well above that.
# app.py uses 1024 as a mere-existence floor; social presented MP4s are far larger.
MIN_PRESENTED_VIDEO_BYTES = 10_000
MEDIA_VALIDITY_PREFIX = "MEDIA_VALIDITY_FAILED"


@dataclass
class MediaProbeInfo:
    exists: bool = False
    file_size: int = 0
    duration: float = 0.0
    frame_count: int = 0
    width: int = 0
    height: int = 0
    decodable: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MediaValidityResult:
    ok: bool
    failure_reason: Optional[str] = None
    probe: Optional[MediaProbeInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"ok": self.ok, "failure_reason": self.failure_reason}
        d["probe"] = self.probe.to_dict() if self.probe else None
        return d


ProbeFn = Callable[[Path], MediaProbeInfo]


def _find_ffprobe() -> Optional[str]:
    env = os.environ.get("FFPROBE_PATH") or os.environ.get("FFMPEG_PATH")
    if env:
        p = Path(env)
        if p.name.lower().startswith("ffmpeg"):
            cand = p.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
            if cand.is_file():
                return str(cand)
        if p.is_file() and "ffprobe" in p.name.lower():
            return str(p)
    which = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    return which


def probe_presented_video(path: Union[str, Path]) -> MediaProbeInfo:
    """ffprobe-based probe (preferred existing project tool)."""
    p = Path(path)
    info = MediaProbeInfo(exists=p.is_file(), file_size=p.stat().st_size if p.is_file() else 0)
    if not info.exists:
        info.error = "missing"
        return info
    ffprobe = _find_ffprobe()
    if not ffprobe:
        info.error = "ffprobe_unavailable"
        return info
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=width,height,nb_frames,nb_read_frames,codec_type",
        "-count_frames",
        "-of",
        "json",
        str(p),
    ]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if run.returncode != 0:
            info.error = f"ffprobe_rc={run.returncode}"
            return info
        data = json.loads(run.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        info.error = f"ffprobe_error:{exc}"
        return info

    format_info = data.get("format") if isinstance(data.get("format"), dict) else {}
    try:
        info.duration = float(str(format_info.get("duration") or "0").strip() or 0)
    except ValueError:
        info.duration = 0.0

    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if str(stream.get("codec_type") or "").lower() != "video":
            continue
        info.decodable = True
        info.width = int(stream.get("width") or 0)
        info.height = int(stream.get("height") or 0)
        nb = stream.get("nb_read_frames") or stream.get("nb_frames") or 0
        try:
            info.frame_count = int(str(nb).strip() or 0)
        except ValueError:
            info.frame_count = 0
        break

    # If duration>0 but frame_count unknown, treat as at least 1 when decodable
    if info.decodable and info.frame_count <= 0 and info.duration > 0:
        info.frame_count = 1
    return info


def validate_presented_social_video(
    path: Union[str, Path],
    *,
    min_bytes: int = MIN_PRESENTED_VIDEO_BYTES,
    expected_width: int = DEFAULT_SOCIAL_WIDTH,
    expected_height: int = DEFAULT_SOCIAL_HEIGHT,
    probe_fn: Optional[ProbeFn] = None,
) -> MediaValidityResult:
    """Validate presented/final social video before SOCIAL_READY.

    Failure reasons use MEDIA_VALIDITY_FAILED:<code> (e.g. too_small).
    """
    p = Path(path)
    if not p.is_file():
        return MediaValidityResult(
            ok=False,
            failure_reason=f"{MEDIA_VALIDITY_PREFIX}:missing",
            probe=MediaProbeInfo(exists=False),
        )
    size = p.stat().st_size
    if size < int(min_bytes):
        return MediaValidityResult(
            ok=False,
            failure_reason=f"{MEDIA_VALIDITY_PREFIX}:too_small",
            probe=MediaProbeInfo(exists=True, file_size=size),
        )

    probe = (probe_fn or probe_presented_video)(p)
    probe.file_size = size
    if not probe.decodable:
        return MediaValidityResult(
            ok=False,
            failure_reason=f"{MEDIA_VALIDITY_PREFIX}:not_decodable",
            probe=probe,
        )
    if probe.frame_count <= 0:
        return MediaValidityResult(
            ok=False,
            failure_reason=f"{MEDIA_VALIDITY_PREFIX}:zero_frames",
            probe=probe,
        )
    if probe.duration <= 0:
        return MediaValidityResult(
            ok=False,
            failure_reason=f"{MEDIA_VALIDITY_PREFIX}:zero_duration",
            probe=probe,
        )
    if probe.width <= 0 or probe.height <= 0:
        return MediaValidityResult(
            ok=False,
            failure_reason=f"{MEDIA_VALIDITY_PREFIX}:missing_dimensions",
            probe=probe,
        )
    if expected_width and expected_height:
        if int(probe.width) != int(expected_width) or int(probe.height) != int(expected_height):
            return MediaValidityResult(
                ok=False,
                failure_reason=(
                    f"{MEDIA_VALIDITY_PREFIX}:dimension_mismatch:"
                    f"got={probe.width}x{probe.height}:expected={expected_width}x{expected_height}"
                ),
                probe=probe,
            )
    return MediaValidityResult(ok=True, failure_reason=None, probe=probe)


def pass_probe_for_tests(
    width: int = DEFAULT_SOCIAL_WIDTH,
    height: int = DEFAULT_SOCIAL_HEIGHT,
    duration: float = 1.0,
    frame_count: int = 25,
) -> ProbeFn:
    """Injectable probe that always reports a valid social video (unit tests)."""

    def _probe(path: Path) -> MediaProbeInfo:
        p = Path(path)
        return MediaProbeInfo(
            exists=p.is_file(),
            file_size=p.stat().st_size if p.is_file() else 0,
            duration=duration,
            frame_count=frame_count,
            width=width,
            height=height,
            decodable=True,
        )

    return _probe
