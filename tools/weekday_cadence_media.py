"""Optional weekday-cadence media step, gated by --with-media.

Design (not run on the real GPU from tests or dry-run):
- Reuse an existing promo image or approved still first.
- Generate a still only when nothing reusable is found.
- Build each TikTok Wan clip through the existing 603cbeb chain, then apply
  the frame probe and SVD social hold already used by weekday_cadence_posts.
- Kai, Kael, Liang, and Jarek stills go to the identity approval batch.
- The GPU is taken only through the existing ExclusiveGpuLease, and only after
  a preflight that requires port 8188 to be free and no Research python/ffmpeg
  process to be running.

Default CLI dry-run never calls this producer. --with-media without --dry-run
still refuses the lease and generation when preflight fails, so a mistaken
invocation cannot start ComfyUI during a Research GPU test.
"""

from __future__ import annotations

import json
import sys

import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from tools.weekday_cadence_config import (
    COMFYUI_PORT,
    DEPICTION_GOVERNED,
    DEPICTION_NOT_GOVERNED,
    DEPICTION_UNKNOWN,
    IDENTITY_CHARACTERS,
    WAN_BACKEND,
)

StillFinder = Callable[[str, int | None], Path | None]
StillGenerator = Callable[[str, int | None], Path | None]
ClipProducer = Callable[..., Any]
ProcessLister = Callable[[], Sequence[Mapping[str, Any]]]
PortChecker = Callable[[int], bool]
LeaseFactory = Callable[[], Any]


class GpuPreflightError(RuntimeError):
    """Raised when the cadence must not take the GPU."""


class CadenceMediaPreflightError(RuntimeError):
    """Raised when --with-media cannot start. No pack should be written."""


def _default_bible_projection() -> Any:
    """CPU-only Studio Bible projection. Does not import app or use the GPU."""
    from tools.studio_bible_adapter import build_projection

    return build_projection("en", 1, "")


def bible_media_preflight(
    *,
    yaml_importer: Callable[[], Any] | None = None,
    projector: Callable[[], Any] | None = None,
    executable: str | None = None,
) -> tuple[bool, str]:
    """Check that yaml imports and a Studio Bible projection has usable canon.

    Returns (ok, message). On failure the message names sys.executable and
    what is missing. This does not change studio_bible_adapter's swallow of a
    missing yaml import; it checks yaml itself first so the failure is clear.
    """
    exe = str(executable or sys.executable)
    nl = chr(10)
    try:
        if yaml_importer is not None:
            yaml_importer()
        else:
            import yaml  # noqa: F401
    except Exception as exc:
        return False, (
            "WEEKDAY_CADENCE_MEDIA_PREFLIGHT_FAILED"
            + nl
            + "interpreter: "
            + exe
            + nl
            + "missing: yaml (import failed: "
            + type(exc).__name__
            + ": "
            + str(exc)
            + ")"
        )

    try:
        projection = projector() if projector is not None else _default_bible_projection()
    except Exception as exc:
        return False, (
            "WEEKDAY_CADENCE_MEDIA_PREFLIGHT_FAILED"
            + nl
            + "interpreter: "
            + exe
            + nl
            + "missing: Studio Bible projection (failed under this interpreter: "
            + type(exc).__name__
            + ": "
            + str(exc)
            + ")"
        )

    n_chars = len(getattr(projection, "characters", None) or ())
    n_locs = len(getattr(projection, "locations", None) or ())
    n_styles = len(getattr(projection, "styles", None) or ())
    missing: list[str] = []
    if n_chars <= 0:
        missing.append("characters")
    if n_locs <= 0:
        missing.append("locations")
    if n_styles <= 0:
        missing.append("style palettes")
    if missing:
        return False, (
            "WEEKDAY_CADENCE_MEDIA_PREFLIGHT_FAILED"
            + nl
            + "interpreter: "
            + exe
            + nl
            + "missing: Studio Bible "
            + ", ".join(missing)
            + " (loaded "
            + str(n_chars)
            + " characters, "
            + str(n_locs)
            + " locations, "
            + str(n_styles)
            + " style palettes; each must be > 0)"
        )
    return True, ""


def check_bible_media_preflight(**kwargs: Any) -> None:
    """Raise CadenceMediaPreflightError when the --with-media bible preflight fails."""
    ok, message = bible_media_preflight(**kwargs)
    if not ok:
        raise CadenceMediaPreflightError(message)


def default_port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        result = sock.connect_ex(("127.0.0.1", int(port)))
        return result != 0
    except OSError:
        return True
    finally:
        sock.close()


def _command_looks_like_research(command: str) -> bool:
    text = str(command or "").lower()
    if not text:
        return False
    markers = (
        "comfyui",
        "comfy_ui",
        "comfy ui",
        "--listen 8188",
        ":8188",
        "research",
        "ffmpeg stress",
        "stress test",
    )
    return any(marker in text for marker in markers)


def list_local_processes() -> list[dict[str, Any]]:
    """Best-effort process list. Never required for tests (they inject a lister)."""
    out: list[dict[str, Any]] = []
    try:
        import subprocess

        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        import json

        payload = json.loads(completed.stdout or "[]")
        if isinstance(payload, dict):
            payload = [payload]
        for row in payload or []:
            if isinstance(row, dict):
                out.append(
                    {
                        "pid": row.get("ProcessId"),
                        "name": str(row.get("Name") or ""),
                        "command": str(row.get("CommandLine") or ""),
                    }
                )
    except Exception:
        return []
    return out


def research_processes(
    processes: Sequence[Mapping[str, Any]] | None = None,
    *,
    lister: ProcessLister | None = None,
) -> list[dict[str, Any]]:
    rows = list(processes if processes is not None else (lister or list_local_processes)())
    found: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("name") or row.get("Name") or "").lower()
        command = str(row.get("command") or row.get("CommandLine") or "")
        if name.startswith("ffmpeg") or name == "ffmpeg.exe":
            found.append(dict(row))
            continue
        if "python" in name and _command_looks_like_research(command):
            found.append(dict(row))
    return found


def gpu_preflight(
    *,
    port: int = COMFYUI_PORT,
    processes: Sequence[Mapping[str, Any]] | None = None,
    port_free: PortChecker | None = None,
    lister: ProcessLister | None = None,
) -> tuple[bool, str]:
    checker = port_free or default_port_free
    if not checker(int(port)):
        return False, f"GPU_PREFLIGHT:COMFY_PORT_BUSY:{port}"
    busy = research_processes(processes, lister=lister)
    if busy:
        return False, "GPU_PREFLIGHT:RESEARCH_PROCESS_RUNNING"
    return True, ""



_GOVERNED_SIDECAR_STATUS = frozenset({"CANONICAL_IDENTITY_GOVERNED"})
_NOT_GOVERNED_SIDECAR_STATUS = frozenset({
    "NOT_APPLICABLE_NO_GOVERNED_CHARACTER",
    "NO_GOVERNED_CHARACTER",
})


def depiction_from_still(path: Path | None) -> str:
    """Structured depiction evidence from the stills pipeline sidecar, if present.

    Missing or unreadable sidecars are unknown. This is never inferred from the
    novel alone.
    """
    if path is None:
        return DEPICTION_UNKNOWN
    image = Path(path)
    side = image.with_name(image.name + ".identity_preservation.json")
    if not side.is_file():
        return DEPICTION_UNKNOWN
    try:
        rec = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEPICTION_UNKNOWN
    if not isinstance(rec, dict):
        return DEPICTION_UNKNOWN
    status = str(rec.get("CANON_DEPICTION_STATUS") or rec.get("DECISION") or "").strip()
    if (
        status in _GOVERNED_SIDECAR_STATUS
        or str(rec.get("APPROVED_CHARACTER_PORTRAIT") or "").strip().upper() == "YES"
        or str(rec.get("CHARACTER_ID") or rec.get("character_id") or "").strip()
    ):
        return DEPICTION_GOVERNED
    if status in _NOT_GOVERNED_SIDECAR_STATUS or status.endswith("NO_GOVERNED_CHARACTER"):
        return DEPICTION_NOT_GOVERNED
    return DEPICTION_UNKNOWN


def identity_character_for(novel: str) -> str | None:
    return IDENTITY_CHARACTERS.get(str(novel).strip().upper())


@dataclass
class StillPlan:
    novel: str
    chapter: int | None
    path: Path | None
    origin: str  # existing_promo | approved_still | generate | missing
    identity_character: str | None = None
    needs_approval: bool = False

    @property
    def reusable(self) -> bool:
        return self.path is not None and self.origin in {"existing_promo", "approved_still"}


@dataclass
class MediaPreparation:
    stills: dict[str, Path] = field(default_factory=dict)
    clips: dict[str, Path] = field(default_factory=dict)
    stills_by_chapter: dict[tuple[str, int], Path] = field(default_factory=dict)
    clips_by_chapter: dict[tuple[str, int], Path] = field(default_factory=dict)
    tiktok_stills: dict[tuple[str, int], Path] = field(default_factory=dict)
    generation_holds: dict[tuple[str, int], str] = field(default_factory=dict)
    identity_needed: dict[str, bool] = field(default_factory=dict)
    plans: list[StillPlan] = field(default_factory=list)
    preflight_ok: bool = True
    preflight_reason: str = ""
    generated: list[str] = field(default_factory=list)
    lease_acquired: bool = False


def plan_still(
    novel: str,
    chapter: int | None,
    *,
    existing: Path | None = None,
    finder: StillFinder | None = None,
) -> StillPlan:
    character = identity_character_for(novel)
    if existing is not None and Path(existing).is_file():
        return StillPlan(
            novel=novel,
            chapter=chapter,
            path=Path(existing),
            origin="existing_promo",
            identity_character=character,
            needs_approval=False,
        )
    found = finder(novel, chapter) if finder is not None else None
    if found is not None and Path(found).is_file():
        return StillPlan(
            novel=novel,
            chapter=chapter,
            path=Path(found),
            origin="approved_still",
            identity_character=character,
            needs_approval=False,
        )
    return StillPlan(
        novel=novel,
        chapter=chapter,
        path=None,
        origin="missing",
        identity_character=character,
        needs_approval=False,
    )


def _acquire_lease(lease: Any, job_id: str) -> None:
    if lease is None:
        return
    kind = getattr(lease, "KIND_I2V", "i2v")
    lease.acquire(job_id, kind, stage="CADENCE_WITH_MEDIA", backend_id=WAN_BACKEND)


def _release_lease(lease: Any, job_id: str) -> None:
    if lease is None:
        return
    try:
        lease.release(job_id)
    except Exception:
        return



def _accepts_size(generate_still) -> bool:
    if generate_still is None:
        return False
    try:
        import inspect

        sig = inspect.signature(generate_still)
    except (TypeError, ValueError):
        return False
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()):
        return True
    return "size" in sig.parameters


def _call_generate_still(generate_still, novel, chapter, size=None):
    """Call generate_still, requesting size only when the callable accepts it."""
    if size is None:
        return generate_still(novel, chapter)
    if not _accepts_size(generate_still):
        return None
    return generate_still(novel, chapter, size=size)


def _still_pixel_size(path: Path | None) -> tuple[int, int] | None:
    if path is None or not Path(path).is_file():
        return None
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def prepare_media(
    *,
    novels: Sequence[str],
    chapters: Mapping[str, int | None],
    with_media: bool,
    dry_run: bool,
    existing_stills: Mapping[str, Path] | None = None,
    finder: StillFinder | None = None,
    generate_still: StillGenerator | None = None,
    produce_clip: ClipProducer | None = None,
    gpu_lease: Any = None,
    lease_factory: LeaseFactory | None = None,
    port: int = COMFYUI_PORT,
    port_free: PortChecker | None = None,
    processes: Sequence[Mapping[str, Any]] | None = None,
    lister: ProcessLister | None = None,
    job_id: str = "weekday-cadence-media",
    items: Sequence[Any] | None = None,
    output_dir: Path | None = None,
    acquire_lease: bool = True,
) -> MediaPreparation:
    """Resolve or (optionally) generate per-novel stills and Wan clips.

    Tests inject stubs for finder, generate_still, produce_clip, lease, and
    preflight. This function never imports ComfyUI or ffmpeg itself.
    """
    result = MediaPreparation()
    if not with_media:
        return result

    existing = dict(existing_stills or {})
    jobs: list[tuple[str, int | None]] = []
    seen: set[tuple[str, int | None]] = set()
    if items:
        for item in items:
            if getattr(item, "platform", "") == "x":
                continue
            novel = str(getattr(item, "novel", "") or "")
            chapter = getattr(item, "source_chapter", None)
            key = (novel, chapter)
            if not novel or key in seen:
                continue
            seen.add(key)
            jobs.append(key)
    if not jobs:
        jobs = [(str(novel), chapters.get(novel)) for novel in novels]

    plans: list[StillPlan] = []
    for novel, chapter in jobs:
        plans.append(
            plan_still(
                novel,
                chapter,
                existing=existing.get(novel),
                finder=finder,
            )
        )
    result.plans = plans
    for plan in plans:
        if plan.needs_approval:
            result.identity_needed[plan.novel] = True
        if plan.path is not None:
            result.stills[plan.novel] = plan.path
            if plan.chapter is not None:
                result.stills_by_chapter[(plan.novel, int(plan.chapter))] = plan.path

    from tools.weekday_cadence_stills import STILL_SIZE_TIKTOK

    needs_generation = [plan for plan in plans if plan.path is None]
    needs_clips = list(plans)
    for plan in plans:
        if plan.path is None or plan.chapter is None:
            continue
        if _still_pixel_size(plan.path) == STILL_SIZE_TIKTOK:
            result.tiktok_stills[(plan.novel, int(plan.chapter))] = plan.path
    can_native_tiktok = _accepts_size(generate_still)
    needs_tiktok = [
        plan
        for plan in plans
        if plan.chapter is not None
        and (plan.novel, int(plan.chapter)) not in result.tiktok_stills
        and can_native_tiktok
    ]
    must_use_gpu = (not dry_run) and (
        bool(needs_generation) or bool(needs_tiktok) or produce_clip is not None
    )

    if dry_run or not must_use_gpu:
        result.preflight_ok, result.preflight_reason = True, "DRY_RUN" if dry_run else ""
        return result

    ok, reason = gpu_preflight(
        port=port, processes=processes, port_free=port_free, lister=lister
    )
    result.preflight_ok = ok
    result.preflight_reason = reason
    if not ok:
        return result

    lease = gpu_lease if gpu_lease is not None else (lease_factory() if lease_factory else None)
    acquired = False
    try:
        if lease is not None and acquire_lease:
            _acquire_lease(lease, job_id)
            acquired = True
            result.lease_acquired = True
        if generate_still is not None:
            from tools.weekday_cadence_stills import STILL_SIZE_TIKTOK, StillGenerationBlocked

            def _record_hold(plan, reason: str) -> None:
                if plan.chapter is not None:
                    result.generation_holds[(plan.novel, int(plan.chapter))] = reason

            def _run_generate(plan, size=None):
                try:
                    if size is None:
                        return _call_generate_still(generate_still, plan.novel, plan.chapter)
                    return _call_generate_still(
                        generate_still, plan.novel, plan.chapter, size=size
                    )
                except StillGenerationBlocked as exc:
                    _record_hold(plan, str(exc))
                    return None
                except Exception as exc:
                    _record_hold(plan, f"STILL_GENERATION_BLOCKED:{type(exc).__name__}")
                    return None

            for plan in needs_generation:
                generated = _run_generate(plan)
                if generated is not None and Path(generated).is_file():
                    plan.path = Path(generated)
                    plan.origin = "generate"
                    result.stills[plan.novel] = plan.path
                    if plan.chapter is not None:
                        result.stills_by_chapter[(plan.novel, int(plan.chapter))] = plan.path
                    result.generated.append(plan.novel)
                    if _still_pixel_size(plan.path) == STILL_SIZE_TIKTOK:
                        result.tiktok_stills[(plan.novel, int(plan.chapter))] = plan.path
                elif plan.chapter is not None and (plan.novel, int(plan.chapter)) not in result.generation_holds:
                    _record_hold(plan, "STILL_GENERATION_MISSING_ARTIFACT")

            for plan in plans:
                if plan.chapter is None or not _accepts_size(generate_still):
                    continue
                key = (plan.novel, int(plan.chapter))
                if key in result.tiktok_stills:
                    continue
                if key in result.generation_holds and plan.path is None:
                    # Square generation already blocked; do not invent a TikTok still.
                    continue
                try:
                    generated = _call_generate_still(
                        generate_still, plan.novel, plan.chapter, size=STILL_SIZE_TIKTOK
                    )
                except Exception:
                    generated = None
                if generated is not None and Path(generated).is_file():
                    if _still_pixel_size(generated) == STILL_SIZE_TIKTOK:
                        result.tiktok_stills[key] = Path(generated)
                        if plan.novel not in result.generated:
                            result.generated.append(plan.novel)
                    # Non-native artifacts are discarded. Never letterbox or pad.
                # TikTok-only failures do not write generation_holds (that map
                # also flags the FB/IG square). Missing TikTok media is held later.

        if produce_clip is not None:
            for plan in needs_clips:
                chapter = plan.chapter
                still = None
                if chapter is not None:
                    still = result.tiktok_stills.get((plan.novel, int(chapter)))
                if still is None:
                    continue
                clip = produce_clip(still, novel=plan.novel, chapter=plan.chapter)
                path = getattr(clip, "path", clip)
                if isinstance(path, Path) and path.is_file():
                    result.clips[plan.novel] = path
                    if chapter is not None:
                        result.clips_by_chapter[(plan.novel, int(chapter))] = path
    finally:
        if acquired:
            _release_lease(lease, job_id)
    return result
