"""Release automation + chapter upload orchestration (Task 5 of the extraction).

Extracts the #4 move-as-is orchestration fns (chapter_review_packs, auto_fix_weak_images,
upload_all_for_chapter) and the self-contained release-automation job-management fns
(build_release_automation_backlog, release_automation_status, release_automation_preflight,
_save_release_automation_runtime, summarize_release_stage_progress).

Per the plan's injection pattern, the not-yet-extracted side-effectors are supplied through
COLLABORATORS with safe stubs by default; app.py wires the real functions at Task 8:
- patreon_builder        -> build_patreon_draft (Patreon/browser, owned by Tasks 6-7)
- x_poster               -> publish_x_post
- fb_assist              -> manual_facebook_assist
- buffer_poster          -> buffer_post_from_folder
- weak_fixer             -> regenerate_weak_images(use_openai=False)
- channels_getter        -> configured_buffer_channels
- approval_inbox_getter  -> approval_inbox
- ensure_chapter_release_queue / release_queue_assignment_status / iso_today
- chrome_debug_available / bundled_node_executable (browser runtime checks)
- release_job_runner     -> run_release_automation_job (the heavy executor; deferred to
                            Task 6/7 where browser_publish/buffer_publish own its collaborators,
                            so we do NOT copy its 200-line body + ~25 guessed collaborators here)
- RELEASE_AUTOMATION_THREAD / PAUSE / STOP (threading.Event runtime state from app.py)

Imports ONLY app_config (constants), app_state, automation_db, release_state (ledger +
atomic JSON + json read), approval_inbox (review surface), promo_copy (read_json_safe +
story_key), and the release_planner module. MUST NOT import app.

Behavior preserved verbatim from app.py. See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 5).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import app_config as config
import app_state as state  # noqa: F401 (reserved for future in-module locks/caches)
import automation_db
import approval_inbox as inbox
import promo_copy as copy
import release_state as rs
import release_planner as planner

# Re-exported config constants used below.
ROOT = config.ROOT
NOVEL_NAMES = config.NOVEL_NAMES
RELEASE_AUTOMATION_STATE_FILE = config.RELEASE_AUTOMATION_STATE_FILE

# release_state provides the ledger + atomic JSON.
chapter_ledger_entry = rs.chapter_ledger_entry
update_chapter_ledger = rs.update_chapter_ledger
chapter_ledger_updates_for_folder = rs.chapter_ledger_updates_for_folder
write_json_atomic = rs.write_json_atomic

# promo_copy provides the pure helpers.
read_json_safe = copy.read_json_safe
story_key = copy.story_key

# approval_inbox provides the review surface (used by chapter_review_packs).
approval_inbox = inbox.approval_inbox

# release_planner is a standalone module imported by app.py.
release_stage_due_targets = planner.release_stage_due_targets


# --- not-yet-extracted collaborators (stubs; wired by app.py at Task 8) ---

REQUIRED_COLLABORATORS = [
    # #4 orchestration side-effectors
    "patreon_builder",
    "x_poster",
    "fb_assist",
    "buffer_poster",
    "weak_fixer",
    "channels_getter",
    "approval_inbox_getter",
    # job-management deps
    "ensure_chapter_release_queue",
    "release_queue_assignment_status",
    "iso_today",
    "chrome_debug_available",
    "bundled_node_executable",
    "release_job_runner",
]

# Runtime threading.Event state (injected as data collaborators from app.py).
RELEASE_AUTOMATION_THREAD = None
RELEASE_AUTOMATION_PAUSE = None
RELEASE_AUTOMATION_STOP = None


def _stub_raise(name: str):
    def _fn(*args, **kwargs):
        raise NotImplementedError(
            f"release_automation: collaborator '{name}' not injected. "
            f"app.py must pass collaborators={{'{name}': <real fn>}} at Task 8."
        )
    return _fn


def _default_collaborators() -> dict[str, Any]:
    return {name: _stub_raise(name) for name in REQUIRED_COLLABORATORS}


def _get(collab: dict[str, Any], name: str):
    fn = collab.get(name)
    if fn is None:
        fn = _stub_raise(name)
    return fn


# --- #4 orchestration fns (verbatim from app.py) ---

def chapter_review_packs(abbr: str | None = None, chapter: int | str | None = None, *, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aggregate every pending pack for a chapter (or the active approval path) for the
    Review & Publish view. Reuses approval_inbox() bucketing; filters to the chosen
    novel/chapter when provided.
    """
    collab = collaborators or _default_collaborators()
    inbox_result = _get(collab, "approval_inbox_getter")()
    if abbr or chapter:
        def matches(item: dict[str, Any]) -> bool:
            if abbr and str(item.get("abbr") or "").upper() != str(abbr).upper():
                return False
            if chapter and str(item.get("chapter") or "").strip() and str(item.get("chapter")) != str(chapter):
                return False
            return True
        for key in ("patreon", "dailyShorts", "deepTikToks", "manualSocial", "youtube"):
            inbox_result[key] = [it for it in inbox_result.get(key, []) if matches(it)]
        inbox_result["total"] = sum(inbox_result.get("counts", {}).values())
    return inbox_result


def auto_fix_weak_images(abbr: str | None = None, chapter: int | str | None = None, *, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    """Locally regenerate weak/rejected pack images (no OpenAI/external API).

    Walks the pending packs for the chapter and runs regenerate_weak_images(folder,
    use_openai=False) so weak art is refreshed with the local diffusers pipeline.
    Returns per-pack results; never posts or publishes.
    """
    collab = collaborators or _default_collaborators()
    packs = chapter_review_packs(abbr, chapter, collaborators=collab)
    folders: list[str] = []
    for key in ("patreon", "dailyShorts", "deepTikToks", "manualSocial", "youtube"):
        for it in packs.get(key, []):
            f = str(it.get("folder") or "")
            if f and f not in folders:
                folders.append(f)
    fixed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for folder in folders:
        try:
            result = _get(collab, "weak_fixer")(folder, use_openai=False)
            fixed.append({"folder": folder, "result": result})
        except Exception as exc:  # noqa: BLE001 - surface per-pack, keep going
            errors.append({"folder": folder, "error": str(exc)})
    return {"ok": not errors, "fixed": fixed, "errors": errors, "folder_count": len(folders)}


def upload_all_for_chapter(
    abbr: str | None = None,
    chapter: int | str | None = None,
    *,
    auto_fix_weak: bool = False,
    collaborators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One-click chain: (optional) local auto-fix-weak, then gate on all-images-approved,
    then trigger every relevant publish assist for the chapter:
      - Patreon draft (free for teasers per #2)
      - X post (publish_x_post)
      - Facebook (manual_facebook_assist)
      - Shorts + Instagram -> Buffer (buffer_post_from_folder)
    Gated: if any pack still needs review, returns blocked=True with the offending items.
    """
    collab = collaborators or _default_collaborators()
    if auto_fix_weak:
        auto_fix_weak_images(abbr, chapter, collaborators=collab)
    packs = chapter_review_packs(abbr, chapter, collaborators=collab)
    needs_review: list[dict[str, Any]] = []
    for key in ("patreon", "dailyShorts", "deepTikToks", "manualSocial"):
        for it in packs.get(key, []):
            if it.get("needsReview") or it.get("needs_review"):
                needs_review.append({**it, "kind": key})
    if needs_review:
        return {
            "ok": False,
            "blocked": True,
            "reason": "Images still need review. Approve all pack images before Upload All.",
            "needs_review": needs_review,
        }
    results: dict[str, Any] = {"patreon": [], "x": [], "facebook": [], "shorts_buffer": [], "instagram_buffer": [], "errors": []}
    for it in packs.get("patreon", []):
        try:
            results["patreon"].append(_get(collab, "patreon_builder")(str(it["folder"]), tier_stage_override=""))
        except Exception as exc:  # noqa: BLE001
            results["errors"].append({"step": "patreon", "folder": it.get("folder"), "error": str(exc)})
    for it in packs.get("manualSocial", []):
        f = str(it.get("folder") or "")
        if not f:
            continue
        try:
            results["x"].append(_get(collab, "x_poster")(f))
        except Exception as exc:  # noqa: BLE001
            results["errors"].append({"step": "x", "folder": f, "error": str(exc)})
        try:
            results["facebook"].append(_get(collab, "fb_assist")(f))
        except Exception as exc:  # noqa: BLE001
            results["errors"].append({"step": "facebook", "folder": f, "error": str(exc)})
    channels = _get(collab, "channels_getter")()
    short_ids = [c["id"] for c in channels if c.get("id") and c.get("service") == "tiktok"]
    ig_ids = [c["id"] for c in channels if c.get("id") and c.get("service") == "instagram"]
    for it in packs.get("dailyShorts", []):
        f = str(it.get("folder") or "")
        if not f:
            continue
        if short_ids:
            try:
                results["shorts_buffer"].append(_get(collab, "buffer_poster")(f, short_ids, "tiktok", "addToQueue"))
            except Exception as exc:  # noqa: BLE001
                results["errors"].append({"step": "shorts_buffer", "folder": f, "error": str(exc)})
        if ig_ids:
            try:
                results["instagram_buffer"].append(_get(collab, "buffer_poster")(f, ig_ids, "instagram", "addToQueue"))
            except Exception as exc:  # noqa: BLE001
                results["errors"].append({"step": "instagram_buffer", "folder": f, "error": str(exc)})
    return {"ok": not results["errors"], "blocked": False, **results}


# --- release-automation job management (verbatim from app.py) ---

def summarize_release_stage_progress(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stage_labels = {
        "inner_disciple": "Inner Disciple",
        "path_initiate": "Path Initiate",
        "royal_road": "Royal Road",
    }
    progress: list[dict[str, Any]] = []
    for stage, label in stage_labels.items():
        stage_jobs = [job for job in jobs if str(job.get("stage") or "") == stage]
        counts: dict[str, int] = {}
        for job in stage_jobs:
            status = str(job.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        verified = [job for job in stage_jobs if str(job.get("status") or "") == "verified"]
        verified.sort(
            key=lambda job: str(job.get("verifiedAt") or job.get("completedAt") or job.get("updatedAt") or ""),
            reverse=True,
        )
        progress.append({
            "stage": stage,
            "label": label,
            "counts": counts,
            "total": len(stage_jobs),
            "active": next((job for job in stage_jobs if str(job.get("status") or "") == "running"), None),
            "next": next((job for job in stage_jobs if str(job.get("status") or "") in {"pending", "retrying"}), None),
            "lastVerified": verified[0] if verified else None,
        })
    return progress


def build_release_automation_backlog(*, include_prepared: bool = False, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    collab = collaborators or _default_collaborators()
    queue = _get(collab, "ensure_chapter_release_queue")(days_ahead=365)
    assignments = [_get(collab, "release_queue_assignment_status")(item) for item in queue.get("assignments", [])]
    targets = release_stage_due_targets(
        assignments,
        today=_get(collab, "iso_today")().isoformat(),
        include_prepared=include_prepared,
        include_scheduled=True,
    )
    assignment_by_key = {str(item.get("key") or ""): item for item in assignments}
    jobs: list[dict[str, Any]] = []
    for target in targets:
        assignment = assignment_by_key.get(str(target.get("key") or ""), {})
        jobs.append({
            **target,
            "scheduledFor": str(target.get("date") or ""),
            "novel": str(assignment.get("novel") or NOVEL_NAMES.get(str(target.get("abbr") or ""), "")),
            "title": str(assignment.get("title") or ""),
            "assignmentKey": str(target.get("key") or ""),
            "releasePlanId": str(assignment.get("releasePlanId") or ""),
        })
    queued = automation_db.enqueue_release_jobs(ROOT, jobs)
    return {
        "ok": True,
        "targets": len(targets),
        "queued": queued,
        "status": release_automation_status(collaborators=collab),
        "message": f"Release automation backlog contains {len(targets)} missing stage job(s).",
    }


def release_automation_status(*, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    jobs = automation_db.list_release_jobs(ROOT, limit=5000)
    counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    active = next((job for job in jobs if job.get("status") == "running"), None)
    failures = [job for job in jobs if job.get("status") in {"blocked", "failed"}]
    thread = RELEASE_AUTOMATION_THREAD
    runtime = read_json_safe(RELEASE_AUTOMATION_STATE_FILE)
    if not isinstance(runtime, dict):
        runtime = {}
    if not str(runtime.get("lastError") or "").strip():
        runtime["failedJob"] = {}
    runtime.update({
        "running": bool(thread and getattr(thread, "is_alive", lambda: False)()),
        "paused": bool(RELEASE_AUTOMATION_PAUSE and RELEASE_AUTOMATION_PAUSE.is_set()),
        "stopRequested": bool(RELEASE_AUTOMATION_STOP and RELEASE_AUTOMATION_STOP.is_set()),
    })
    return {
        "ok": True,
        "counts": counts,
        "total": len(jobs),
        "active": active,
        "next": next((job for job in jobs if job.get("status") in {"pending", "retrying"}), None),
        "failures": failures[:25],
        "jobs": jobs[:100],
        "stageProgress": summarize_release_stage_progress(jobs),
        "runtime": runtime,
    }


def release_automation_preflight(*, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    collab = collaborators or _default_collaborators()
    browser_ready, browser_message = _get(collab, "chrome_debug_available")()
    node_path = _get(collab, "bundled_node_executable")()
    jobs = automation_db.list_release_jobs(ROOT, statuses=["pending", "retrying"], limit=5000)
    checks = {
        "chromeBridge": browser_ready,
        "playwrightRuntime": bool(node_path and Path(node_path).exists()),
        "queueReadable": True,
    }
    issues = []
    if not checks["chromeBridge"]:
        issues.append(browser_message)
    if not checks["playwrightRuntime"]:
        issues.append("The bundled browser automation runtime is missing.")
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "browser": browser_message,
        "pendingJobs": len(jobs),
        "issues": issues,
    }


def _save_release_automation_runtime(**updates: Any) -> dict[str, Any]:
    state = read_json_safe(RELEASE_AUTOMATION_STATE_FILE)
    if not isinstance(state, dict):
        state = {}
    state.update(updates)
    state["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json_atomic(RELEASE_AUTOMATION_STATE_FILE, state)
    return state
