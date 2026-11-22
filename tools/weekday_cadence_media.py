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

import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from tools.weekday_cadence_config import (
    COMFYUI_PORT,
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
            needs_approval=character is not None,
        )
    found = finder(novel, chapter) if finder is not None else None
    if found is not None and Path(found).is_file():
        return StillPlan(
            novel=novel,
            chapter=chapter,
            path=Path(found),
            origin="approved_still",
            identity_character=character,
            needs_approval=character is not None,
        )
    return StillPlan(
        novel=novel,
        chapter=chapter,
        path=None,
        origin="missing",
        identity_character=character,
        needs_approval=character is not None,
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
) -> MediaPreparation:
    """Resolve or (optionally) generate per-novel stills and Wan clips.

    Tests inject stubs for finder, generate_still, produce_clip, lease, and
    preflight. This function never imports ComfyUI or ffmpeg itself.
    """
    result = MediaPreparation()
    if not with_media:
        return result

    existing = dict(existing_stills or {})
    plans: list[StillPlan] = []
    for novel in novels:
        plans.append(
            plan_still(
                novel,
                chapters.get(novel),
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

    needs_generation = [plan for plan in plans if plan.path is None]
    needs_clips = list(plans)
    must_use_gpu = (not dry_run) and (bool(needs_generation) or produce_clip is not None)

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
        if lease is not None:
            _acquire_lease(lease, job_id)
            acquired = True
            result.lease_acquired = True
        if generate_still is not None:
            for plan in needs_generation:
                generated = generate_still(plan.novel, plan.chapter)
                if generated is not None and Path(generated).is_file():
                    plan.path = Path(generated)
                    plan.origin = "generate"
                    result.stills[plan.novel] = plan.path
                    result.generated.append(plan.novel)
        if produce_clip is not None:
            for plan in needs_clips:
                still = result.stills.get(plan.novel)
                if still is None:
                    continue
                clip = produce_clip(still, novel=plan.novel, chapter=plan.chapter)
                path = getattr(clip, "path", clip)
                if isinstance(path, Path) and path.is_file():
                    result.clips[plan.novel] = path
    finally:
        if acquired:
            _release_lease(lease, job_id)
    return result
