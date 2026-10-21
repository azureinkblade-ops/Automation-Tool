"""Queue-aware chapter write/publish planner.

Pure planning layer. Does not call Patreon or Royal Road. Does not import app.py.
Use dry_run=True (default) to compute the next action without publishing.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from release_planner import parse_date, propose_release_dates

MIN_WORDS = 3000
PREFERRED_MAX_WORDS = 5000
MAX_CONTINUATION_ATTEMPTS = 3
PROMPT_LEAK_MARKERS = (
    "Write the next chapter",
    "Target length:",
    "Chapter Brief:",
    "manual_required",
    "api_generation_disabled",
    "Continuity and style notes:",
    "[truncated]",
    "...[truncated]",
)
TRUNCATION_TAILS = (
    "...[truncated]",
    "[truncated]",
    "\ufffd",
)

STAGES = (
    "determine_chapter",
    "load_previous",
    "generate",
    "validate",
    "schedule",
    "upload_inner_disciple",
    "upload_path_initiate",
    "upload_royal_road",
    "record",
    "complete",
)


def extract_chapter_prose(text: str, chapter_number: int) -> str:
    """Drop model preamble and keep from the Chapter N header onward."""
    body = text or ""
    pattern = re.compile(rf"^Chapter\s+{int(chapter_number)}\s*[-:].*", re.I | re.M)
    match = pattern.search(body)
    if match:
        return body[match.start() :].strip()
    return body.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def determine_next_chapter(
    *,
    latest_valid_chapter: int,
    generated_chapter: int | None = None,
    uploaded_chapter: int | None = None,
    scheduled_chapter: int | None = None,
) -> dict[str, Any]:
    """Next chapter is latest valid + 1. Never reuse or skip a number."""
    latest = int(latest_valid_chapter or 0)
    next_chapter = latest + 1
    already_generated = int(generated_chapter or 0) == next_chapter
    already_uploaded = int(uploaded_chapter or 0) == next_chapter
    already_scheduled = int(scheduled_chapter or 0) == next_chapter
    return {
        "previousChapter": latest,
        "nextChapter": next_chapter,
        "alreadyGenerated": already_generated,
        "alreadyUploaded": already_uploaded,
        "alreadyScheduled": already_scheduled,
        "wouldGenerate": not already_generated,
    }


def _first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""


def _parse_title(first_line: str, chapter_number: int) -> str:
    match = re.match(rf"^Chapter\s+{chapter_number}\s*[-:]\s*(.+)$", first_line, re.I)
    if match:
        return match.group(1).strip()
    return ""


def validate_chapter(
    *,
    text: str,
    chapter_number: int,
    previous_loaded: bool,
    previous_text: str = "",
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    body = text or ""
    first = _first_line(body)
    title = _parse_title(first, chapter_number)
    count = word_count(body)
    if not first:
        errors.append("MISSING_BODY")
    if not title:
        errors.append("MISSING_TITLE")
    if not re.match(rf"^Chapter\s+{chapter_number}\b", first, re.I):
        errors.append("WRONG_CHAPTER_NUMBER")
    if not previous_loaded:
        errors.append("PREVIOUS_CHAPTER_NOT_LOADED")
    if count < MIN_WORDS:
        errors.append("BELOW_MIN_WORD_COUNT")
    if count > PREFERRED_MAX_WORDS:
        warnings.append("OVER_PREFERRED_MAX_WORD_COUNT")
    if previous_text and body.strip() == previous_text.strip():
        errors.append("IDENTICAL_TO_PREVIOUS")
    lowered = body.lower()
    if any(marker.lower() in lowered for marker in PROMPT_LEAK_MARKERS):
        errors.append("PROMPT_LEAK")
    stripped = body.rstrip()
    if any(stripped.endswith(tail) for tail in TRUNCATION_TAILS) or stripped.endswith("..."):
        errors.append("TRUNCATED")
    if "```" in body:
        errors.append("MARKDOWN_FENCE")
    if "\u2014" in body:
        errors.append("EM_DASH")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "wordCount": count,
        "title": title,
        "previousChapterLoaded": previous_loaded,
        "reviewRequired": count > PREFERRED_MAX_WORDS,
    }


def _yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def format_dry_run(plan: dict[str, Any]) -> str:
    lines = [
        f"NOVEL={plan.get('novel', '')}",
        f"PREVIOUS_CHAPTER={plan.get('previousChapter', '')}",
        f"NEXT_CHAPTER={plan.get('nextChapter', '')}",
        f"PREVIOUS_CHAPTER_LOADED={_yes_no(bool(plan.get('previousChapterLoaded')))}",
        f"CHAPTER_ALREADY_GENERATED={_yes_no(bool(plan.get('chapterAlreadyGenerated')))}",
        f"WORD_COUNT={plan.get('wordCount', '')}",
        f"LAST_QUEUED_INNER_DISCIPLE={plan.get('lastQueuedInnerDisciple', '')}",
        f"INNER_DISCIPLE_DATE={plan.get('innerDiscipleDate', '')}",
        f"PATH_INITIATE_DATE={plan.get('pathInitiateDate', '')}",
        f"ROYAL_ROAD_DATE={plan.get('royalRoadDate', '')}",
        f"INNER_DISCIPLE_EXISTING={_yes_no(bool(plan.get('innerDiscipleExisting')))}",
        f"PATH_INITIATE_EXISTING={_yes_no(bool(plan.get('pathInitiateExisting')))}",
        f"ROYAL_ROAD_EXISTING={_yes_no(bool(plan.get('royalRoadExisting')))}",
        f"WOULD_GENERATE={_yes_no(bool(plan.get('wouldGenerate')))}",
        f"WOULD_UPLOAD_INNER_DISCIPLE={_yes_no(bool(plan.get('wouldUploadInner')))}",
        f"WOULD_UPLOAD_PATH_INITIATE={_yes_no(bool(plan.get('wouldUploadPath')))}",
        f"WOULD_UPLOAD_PATREON={_yes_no(bool(plan.get('wouldUploadPatreon')))}",
        f"WOULD_UPLOAD_ROYAL_ROAD={_yes_no(bool(plan.get('wouldUploadRoyalRoad')))}",
        f"NEXT_INCOMPLETE_STAGE={plan.get('nextIncompleteStage', '')}",
        f"DUPLICATE_CHECK={plan.get('duplicateCheck', '')}",
        f"SCHEDULE_CONFLICT_CHECK={plan.get('scheduleConflictCheck', '')}",
        f"WORKFLOW_STATUS={plan.get('workflowStatus', '')}",
    ]
    return "\n".join(lines)


def plan_chapter_workflow(
    *,
    novel: str,
    today: date,
    latest_valid_chapter: int,
    previous_loaded: bool,
    previous_inner: date | None = None,
    generated_chapter: int | None = None,
    uploaded_chapter: int | None = None,
    scheduled_chapter: int | None = None,
    inner_existing: bool = False,
    path_existing: bool = False,
    royal_existing: bool = False,
    existing_future_inners: set[date] | list[date] | None = None,
    occupied_inner: set[date] | None = None,
    occupied_path: set[date] | None = None,
    occupied_royal: set[date] | None = None,
    already_scheduled: dict[str, Any] | None = None,
    chapter_text: str = "",
    previous_text: str = "",
    dry_run: bool = True,
    remote_state_ambiguous: bool = False,
) -> dict[str, Any]:
    """State-aware dry-run / publish plan. Never performs live uploads."""
    numbering = determine_next_chapter(
        latest_valid_chapter=latest_valid_chapter,
        generated_chapter=generated_chapter,
        uploaded_chapter=uploaded_chapter,
        scheduled_chapter=scheduled_chapter,
    )
    next_chapter = numbering["nextChapter"]
    already = already_scheduled or {}
    if inner_existing and not already.get("innerDiscipleDate"):
        already = dict(already)
    dates = propose_release_dates(
        today=today,
        previous_inner=previous_inner,
        existing_future_inners=existing_future_inners,
        occupied_inner=occupied_inner,
        occupied_path=occupied_path,
        occupied_royal=occupied_royal,
        already_scheduled=already if (inner_existing or already) else None,
    )
    validation = None
    if chapter_text:
        validation = validate_chapter(
            text=chapter_text,
            chapter_number=next_chapter,
            previous_loaded=previous_loaded,
            previous_text=previous_text,
        )
    duplicate = "CLEAR"
    if numbering["alreadyUploaded"]:
        duplicate = "ALREADY_UPLOADED"
    elif numbering["alreadyGenerated"]:
        duplicate = "ALREADY_GENERATED"
    conflict = "CLEAR" if dates["ok"] else "CONFLICT:" + ",".join(dates["conflicts"])
    status = "DRY_RUN" if dry_run else "READY"
    if remote_state_ambiguous:
        status = "BLOCKED_AMBIGUOUS_REMOTE"
    elif not dates["ok"]:
        status = "BLOCKED_SCHEDULE_CONFLICT"
    elif validation and not validation["ok"]:
        status = "BLOCKED_VALIDATION"
    elif numbering["previousChapter"] > 0 and not previous_loaded:
        status = "BLOCKED_PREVIOUS_NOT_LOADED"
    would_generate = numbering["wouldGenerate"] and status not in {
        "BLOCKED_AMBIGUOUS_REMOTE",
        "BLOCKED_PREVIOUS_NOT_LOADED",
        "BLOCKED_SCHEDULE_CONFLICT",
        "BLOCKED_VALIDATION",
    }
    would_upload_inner = (
        not inner_existing
        and status in {"DRY_RUN", "READY"}
        and not numbering["alreadyUploaded"]
    )
    would_upload_path = (
        not path_existing
        and status in {"DRY_RUN", "READY"}
        and not numbering["alreadyUploaded"]
    )
    would_upload_patreon = would_upload_inner or would_upload_path
    would_upload_royal = (
        not royal_existing
        and status in {"DRY_RUN", "READY"}
        and not numbering["alreadyUploaded"]
    )
    if remote_state_ambiguous:
        would_generate = False
        would_upload_inner = False
        would_upload_path = False
        would_upload_patreon = False
        would_upload_royal = False
    word_count_value = (validation or {}).get("wordCount", "")
    last_queued = ""
    if existing_future_inners:
        dated = [item for item in existing_future_inners if isinstance(item, date)]
        if dated:
            last_queued = max(dated).isoformat()
    next_stage = "complete"
    if numbering["wouldGenerate"]:
        next_stage = "generate"
    elif validation and not validation.get("ok"):
        next_stage = "validate"
    elif would_upload_inner:
        next_stage = "upload_inner_disciple"
    elif would_upload_path:
        next_stage = "upload_path_initiate"
    elif would_upload_royal:
        next_stage = "upload_royal_road"
    plan = {
        "novel": novel,
        "previousChapter": numbering["previousChapter"],
        "nextChapter": next_chapter,
        "previousChapterLoaded": previous_loaded if numbering["previousChapter"] > 0 else True,
        "chapterAlreadyGenerated": numbering["alreadyGenerated"],
        "wordCount": word_count_value,
        "lastQueuedInnerDisciple": last_queued,
        "wouldGenerate": would_generate,
        "wouldUploadInner": would_upload_inner,
        "wouldUploadPath": would_upload_path,
        "wouldUploadPatreon": would_upload_patreon,
        "wouldUploadRoyalRoad": would_upload_royal,
        "nextIncompleteStage": next_stage,
        "innerDiscipleDate": dates["innerDiscipleDate"],
        "pathInitiateDate": dates["pathInitiateDate"],
        "royalRoadDate": dates["royalRoadDate"],
        "innerDiscipleExisting": inner_existing,
        "pathInitiateExisting": path_existing,
        "royalRoadExisting": royal_existing,
        "duplicateCheck": duplicate,
        "scheduleConflictCheck": conflict,
        "workflowStatus": status,
        "dryRun": dry_run,
        "validation": validation,
        "dates": dates,
        "numbering": numbering,
    }
    plan["preview"] = format_dry_run(plan)
    return plan


def durable_remote_id(value: Any) -> str:
    return str(value or "").strip()


def upload_confirmed(record: dict[str, Any], uploaded_key: str, id_key: str) -> bool:
    return bool(record.get(uploaded_key)) and bool(durable_remote_id(record.get(id_key)))


def upload_missing_durable_id(record: dict[str, Any], uploaded_key: str, id_key: str) -> bool:
    return bool(record.get(uploaded_key)) and not durable_remote_id(record.get(id_key))


def next_missing_patreon_chapter(
    saved_chapters: list[Any] | set[Any],
    complete_chapters: list[Any] | set[Any],
) -> int | None:
    """Oldest saved chapter after the latest Patreon-complete chapter.

    Newest written is not proof that earlier Patreon stages are done.
    """
    saved: list[int] = []
    for item in saved_chapters or []:
        try:
            saved.append(int(item))
        except (TypeError, ValueError):
            continue
    complete: set[int] = set()
    for item in complete_chapters or []:
        try:
            complete.add(int(item))
        except (TypeError, ValueError):
            continue
    last_complete = max(complete) if complete else 0
    for number in sorted(set(saved)):
        if number > last_complete and number not in complete:
            return number
    return None


def next_incomplete_stage(record: dict[str, Any]) -> str:
    """Resume after a partial run. Skip stages already confirmed."""
    if not record.get("generated"):
        return "generate"
    if not record.get("validated") and not record.get("saved"):
        return "validate"
    if not record.get("scheduled"):
        return "schedule"
    if not upload_confirmed(record, "innerDiscipleUploaded", "innerDisciplePostId"):
        return "upload_inner_disciple"
    if not upload_confirmed(record, "pathInitiateUploaded", "pathInitiatePostId"):
        return "upload_path_initiate"
    if not upload_confirmed(record, "royalRoadUploaded", "royalRoadChapterId"):
        return "upload_royal_road"
    if not record.get("recorded"):
        return "record"
    return "complete"


def load_workflow_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_workflow_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(path)


def resume_actions(record: dict[str, Any]) -> dict[str, bool]:
    """Idempotent action flags for a retry after partial success."""
    stage = next_incomplete_stage(record)
    return {
        "regenerate": stage == "generate",
        "reuploadPatreonInner": stage == "upload_inner_disciple",
        "reuploadPatreonPath": stage == "upload_path_initiate",
        "reuploadRoyalRoad": stage == "upload_royal_road",
        "stage": stage,
    }


def workflow_log_fields(plan: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    return {
        "NOVEL": plan.get("novel"),
        "PREVIOUS_CHAPTER": plan.get("previousChapter"),
        "NEXT_CHAPTER": plan.get("nextChapter"),
        "PREVIOUS_CHAPTER_SOURCE": record.get("previousChapterSource", ""),
        "PREVIOUS_CHAPTER_LOADED": plan.get("previousChapterLoaded"),
        "GENERATED": bool(record.get("generated") or not plan.get("wouldGenerate")),
        "WORD_COUNT": (plan.get("validation") or {}).get("wordCount"),
        "CONTINUITY_VALIDATED": bool((plan.get("validation") or {}).get("ok")),
        "PATREON_POST_ID": record.get("patreonPostId", ""),
        "INNER_DISCIPLE_DATE": plan.get("innerDiscipleDate"),
        "PATH_INITIATE_DATE": plan.get("pathInitiateDate"),
        "ROYAL_ROAD_CHAPTER_ID": record.get("royalRoadChapterId", ""),
        "ROYAL_ROAD_DATE": plan.get("royalRoadDate"),
        "DUPLICATE_CHECK": plan.get("duplicateCheck"),
        "SCHEDULE_CONFLICT_CHECK": plan.get("scheduleConflictCheck"),
        "WORKFLOW_STATUS": plan.get("workflowStatus"),
        "INNER_DISCIPLE_STATUS": record.get("innerDiscipleStatus", ""),
        "INNER_DISCIPLE_POST_ID": record.get("innerDisciplePostId") or record.get("patreonPostId", ""),
        "PATH_INITIATE_STATUS": record.get("pathInitiateStatus", ""),
        "PATH_INITIATE_POST_ID": record.get("pathInitiatePostId", ""),
        "ROYAL_ROAD_STATUS": record.get("royalRoadStatus", ""),
        "WORKFLOW_STAGE": next_incomplete_stage(record) if record else plan.get("nextIncompleteStage", ""),
        "LAST_ERROR": record.get("lastError", ""),
        "CHAPTER_TITLE": record.get("chapterTitle") or (plan.get("validation") or {}).get("title", ""),
        "CHAPTER_NUMBER": plan.get("nextChapter"),
    }


def chapter_number_already_exists(existing_numbers: list[Any] | set[Any], chapter_number: int | str) -> bool:
    try:
        target = int(chapter_number)
    except (TypeError, ValueError):
        return False
    found: set[int] = set()
    for item in existing_numbers or []:
        try:
            found.add(int(item))
        except (TypeError, ValueError):
            continue
    return target in found


def _env_flag(env: dict[str, str] | None, name: str) -> bool:
    source = env if env is not None else {}
    flag = str(source.get(name, "0")).strip().lower()
    return flag not in {"", "0", "false", "no", "off"}


def live_publish_forced_dry_run(requested_dry_run: bool, env: dict[str, str] | None = None) -> bool:
    """True when no live remote stage is authorized."""
    if requested_dry_run:
        return True
    return not (live_patreon_allowed(env) or live_royal_road_allowed(env))


def live_publish_allowed(env: dict[str, str] | None = None) -> bool:
    """Any remote publish. Does not imply Royal Road."""
    return live_patreon_allowed(env) or live_royal_road_allowed(env)


def live_patreon_allowed(env: dict[str, str] | None = None) -> bool:
    """Patreon Inner Disciple / Path Initiate only. CHAPTER_LIVE_PUBLISH does not enable this."""
    return _env_flag(env, "CHAPTER_LIVE_PATREON")


def live_royal_road_allowed(env: dict[str, str] | None = None) -> bool:
    """Royal Road only. CHAPTER_LIVE_PUBLISH does not enable this."""
    return _env_flag(env, "CHAPTER_LIVE_ROYAL_ROAD")


def build_chapter_generation_prompt(
    *,
    novel: str,
    novel_name: str,
    chapter_number: int,
    previous_number: int,
    previous_text: str,
    continuity: str = "",
) -> str:
    return f"""Write Chapter {chapter_number} of the web novel {novel_name} ({novel}).

PREVIOUS_CHAPTER_NUMBER={previous_number}
The immediately preceding chapter is the primary continuity source. Continue directly from it.

Previous chapter (full text):
{previous_text}

Supporting continuity/style/arc context:
{continuity}

Requirements:
- First line: Chapter {chapter_number} - <Title>
- MINIMUM_WORDS={MIN_WORDS}
- PREFERRED_RANGE=3000-4500
- TARGET_MAX={PREFERRED_MAX_WORDS}
- Direct continuation from the previous chapter
- Preserve character motivations, established POV/style, and worldbuilding/canon
- Resolve or advance the immediate previous-chapter momentum
- End with a meaningful hook into the following chapter
- No em dashes
- No markdown fences, author notes, prompt instructions, or meta-commentary
- Do not truncate
"""


def build_continue_draft_prompt(
    *,
    novel: str,
    novel_name: str,
    chapter_number: int,
    draft: str,
    previous_text: str,
) -> str:
    return f"""Continue and revise this existing draft of {novel_name} ({novel}) Chapter {chapter_number}.
Do not regenerate from scratch. Keep the existing prose, scene continuity, and chapter direction.

Previous chapter (primary continuity source):
{previous_text}

Current draft:
{draft}

Add only what is needed to reach at least {MIN_WORDS} words while staying near 3000-4500 and under {PREFERRED_MAX_WORDS} if the scene allows.
No em dashes. No markdown fences. No prompt leakage.
"""


class PublishAdapters:
    """Injected side effects. Tests pass fakes. Production wires existing Patreon/RR functions."""

    def __init__(
        self,
        load_previous=None,
        generate=None,
        continue_draft=None,
        save=None,
        schedule=None,
        upload_inner=None,
        upload_path=None,
        upload_royal=None,
        remote_lookup=None,
    ):
        self.load_previous = load_previous
        self.generate = generate
        self.continue_draft = continue_draft
        self.save = save
        self.schedule = schedule
        self.upload_inner = upload_inner
        self.upload_path = upload_path
        self.upload_royal = upload_royal
        self.remote_lookup = remote_lookup


def run_chapter_workflow(
    *,
    novel: str,
    today: date,
    latest_valid_chapter: int,
    adapters: PublishAdapters,
    record_path: Path | None = None,
    dry_run: bool = True,
    env: dict[str, str] | None = None,
    existing_future_inners: set[date] | list[date] | None = None,
    occupied_inner: set[date] | None = None,
    occupied_path: set[date] | None = None,
    occupied_royal: set[date] | None = None,
    previous_inner: date | None = None,
    inner_existing: bool = False,
    path_existing: bool = False,
    royal_existing: bool = False,
    already_scheduled: dict[str, Any] | None = None,
    existing_chapter_numbers: list[Any] | None = None,
    chapter_text: str = "",
) -> dict[str, Any]:
    """Single production path. Dry-run uses the same planning up to the upload boundary."""
    allow_live_patreon = live_patreon_allowed(env)
    allow_live_royal = live_royal_road_allowed(env)
    record = load_workflow_record(record_path) if record_path else {}
    previous_number = int(latest_valid_chapter or 0)
    previous_text = ""
    previous_source = "NONE"
    previous_loaded = previous_number <= 0
    if previous_number > 0:
        loaded = None
        if adapters.load_previous:
            loaded = adapters.load_previous(novel, previous_number)
        if not loaded or not str(loaded.get("text") or "").strip():
            plan = plan_chapter_workflow(
                novel=novel,
                today=today,
                latest_valid_chapter=previous_number,
                previous_loaded=False,
                previous_inner=previous_inner,
                existing_future_inners=existing_future_inners,
                occupied_inner=occupied_inner,
                occupied_path=occupied_path,
                occupied_royal=occupied_royal,
                already_scheduled=already_scheduled,
                inner_existing=inner_existing,
                path_existing=path_existing,
                royal_existing=royal_existing,
                dry_run=dry_run,
            )
            plan["workflowStatus"] = "BLOCKED_PREVIOUS_NOT_LOADED"
            plan["wouldGenerate"] = False
            plan["wouldUploadInner"] = False
            plan["wouldUploadPath"] = False
            plan["wouldUploadPatreon"] = False
            plan["wouldUploadRoyalRoad"] = False
            plan["PREVIOUS_CHAPTER_NUMBER"] = previous_number
            plan["PREVIOUS_CHAPTER_SOURCE"] = ""
            plan["preview"] = format_dry_run(plan)
            plan["sideEffects"] = []
            return plan
        previous_text = str(loaded.get("text") or "")
        previous_source = str(loaded.get("source") or "previous-chapter")
        previous_loaded = True

    if already_scheduled is None and record.get("scheduled"):
        already_scheduled = {
            "innerDiscipleDate": record.get("innerDiscipleDate"),
            "pathInitiateDate": record.get("pathInitiateDate"),
            "royalRoadDate": record.get("royalRoadDate"),
        }
    numbering = determine_next_chapter(
        latest_valid_chapter=previous_number,
        generated_chapter=record.get("chapterNumber") if record.get("generated") else None,
        uploaded_chapter=None,
        scheduled_chapter=record.get("chapterNumber") if record.get("scheduled") else None,
    )
    next_chapter = numbering["nextChapter"]
    if chapter_number_already_exists(existing_chapter_numbers or [], next_chapter) and not record.get("generated"):
        numbering["alreadyGenerated"] = True
        numbering["wouldGenerate"] = False

    remote = {}
    if adapters.remote_lookup:
        remote = adapters.remote_lookup(novel, next_chapter) or {}
    ambiguous = bool(remote.get("ambiguous"))
    if remote.get("innerExists"):
        inner_existing = True
    if remote.get("pathExists"):
        path_existing = True
    if remote.get("royalExists"):
        royal_existing = True
    inner_existing = inner_existing or bool(record.get("innerDiscipleUploaded"))
    path_existing = path_existing or bool(record.get("pathInitiateUploaded"))
    royal_existing = royal_existing or bool(record.get("royalRoadUploaded"))

    working_text = extract_chapter_prose(chapter_text or record.get("chapterText") or "", next_chapter)
    stage = next_incomplete_stage(record) if record else "generate"
    side_effects: list[str] = []

    if not dry_run and stage in {"generate", "continue"} and numbering["wouldGenerate"]:
        if working_text and word_count(working_text) >= MIN_WORDS:
            record["generated"] = True
            record["chapterNumber"] = next_chapter
            record["chapterText"] = working_text
            if record_path:
                save_workflow_record(record_path, record)
        else:
            try:
                if (not working_text) and adapters.generate:
                    working_text = adapters.generate(novel, next_chapter, previous_text) or working_text
                    working_text = extract_chapter_prose(working_text, next_chapter)
                    side_effects.append("generate")
            except Exception as exc:
                record["lastError"] = str(exc)
                record["generated"] = False
                if record_path:
                    save_workflow_record(record_path, record)
                plan = plan_chapter_workflow(
                    novel=novel,
                    today=today,
                    latest_valid_chapter=previous_number,
                    previous_loaded=previous_loaded,
                    previous_inner=previous_inner,
                    existing_future_inners=existing_future_inners,
                    occupied_inner=occupied_inner,
                    occupied_path=occupied_path,
                    occupied_royal=occupied_royal,
                    already_scheduled=already_scheduled,
                    inner_existing=inner_existing,
                    path_existing=path_existing,
                    royal_existing=royal_existing,
                    dry_run=dry_run,
                    remote_state_ambiguous=ambiguous,
                )
                plan["workflowStatus"] = "BLOCKED_GENERATION"
                plan["PREVIOUS_CHAPTER_NUMBER"] = previous_number
                plan["PREVIOUS_CHAPTER_SOURCE"] = previous_source
                plan["sideEffects"] = side_effects
                plan["record"] = record
                plan["lastError"] = str(exc)
                return plan
            attempts = 0
            while (
                working_text
                and word_count(working_text) < MIN_WORDS
                and adapters.continue_draft
                and attempts < MAX_CONTINUATION_ATTEMPTS
            ):
                working_text = adapters.continue_draft(novel, next_chapter, working_text, previous_text) or working_text
                working_text = extract_chapter_prose(working_text, next_chapter)
                attempts += 1
                side_effects.append("continue_draft")
            record["continuationAttempts"] = attempts
            record["generated"] = bool(working_text)
            record["chapterNumber"] = next_chapter
            record["chapterText"] = working_text
            record["needsContinuation"] = bool(working_text) and word_count(working_text) < MIN_WORDS
            if record_path:
                save_workflow_record(record_path, record)

    plan = plan_chapter_workflow(
        novel=novel,
        today=today,
        latest_valid_chapter=previous_number,
        previous_loaded=previous_loaded,
        previous_inner=previous_inner,
        generated_chapter=next_chapter if (record.get("generated") or numbering["alreadyGenerated"] or working_text) else None,
        uploaded_chapter=next_chapter if (
            upload_confirmed(record, "innerDiscipleUploaded", "innerDisciplePostId")
            and upload_confirmed(record, "pathInitiateUploaded", "pathInitiatePostId")
            and upload_confirmed(record, "royalRoadUploaded", "royalRoadChapterId")
        ) else None,
        scheduled_chapter=next_chapter if record.get("scheduled") else None,
        inner_existing=inner_existing,
        path_existing=path_existing,
        royal_existing=royal_existing,
        existing_future_inners=existing_future_inners,
        occupied_inner=occupied_inner,
        occupied_path=occupied_path,
        occupied_royal=occupied_royal,
        already_scheduled=already_scheduled,
        chapter_text=working_text,
        previous_text=previous_text,
        dry_run=dry_run,
        remote_state_ambiguous=ambiguous,
    )
    plan["PREVIOUS_CHAPTER_NUMBER"] = previous_number
    plan["PREVIOUS_CHAPTER_SOURCE"] = previous_source
    plan["sideEffects"] = [] if dry_run else side_effects
    plan["record"] = record
    if dry_run:
        plan["nextIncompleteStage"] = next_incomplete_stage(record) if record else plan.get("nextIncompleteStage")
        return plan

    if plan["workflowStatus"] not in {"READY", "DRY_RUN"}:
        return plan

    validation = plan.get("validation") or validate_chapter(
        text=working_text,
        chapter_number=next_chapter,
        previous_loaded=previous_loaded,
        previous_text=previous_text,
    )
    if working_text and word_count(working_text) < MIN_WORDS:
        plan["workflowStatus"] = "BLOCKED_VALIDATION"
        plan["wouldUploadInner"] = False
        plan["wouldUploadPath"] = False
        plan["wouldUploadPatreon"] = False
        plan["wouldUploadRoyalRoad"] = False
        return plan

    if adapters.save and working_text and not record.get("saved"):
        try:
            adapters.save(novel, next_chapter, working_text)
        except Exception as exc:
            record["lastError"] = str(exc)
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_SAVE"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            return plan
        record["saved"] = True
        record["generated"] = True
        side_effects.append("save")
        if record_path:
            save_workflow_record(record_path, record)

    if adapters.schedule and not record.get("scheduled"):
        try:
            adapters.schedule(novel, next_chapter, plan["dates"])
        except Exception as exc:
            record["lastError"] = str(exc)
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_SCHEDULE"
            plan["nextIncompleteStage"] = "schedule"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            return plan
        record["scheduled"] = True
        record["innerDiscipleDate"] = plan["innerDiscipleDate"]
        record["pathInitiateDate"] = plan["pathInitiateDate"]
        record["royalRoadDate"] = plan["royalRoadDate"]
        side_effects.append("schedule")
        if record_path:
            save_workflow_record(record_path, record)

    if allow_live_patreon and not dry_run and upload_missing_durable_id(
        record, "innerDiscipleUploaded", "innerDisciplePostId"
    ):
        record["innerDiscipleStatus"] = "AMBIGUOUS"
        record["lastError"] = "Inner Disciple marked uploaded without a durable post ID. Fail closed."
        record["complete"] = False
        if record_path:
            save_workflow_record(record_path, record)
        plan["workflowStatus"] = "BLOCKED_AMBIGUOUS_INNER_DISCIPLE"
        plan["nextIncompleteStage"] = "upload_inner_disciple"
        plan["sideEffects"] = side_effects
        plan["record"] = record
        plan["log"] = workflow_log_fields(plan, record)
        return plan

    if allow_live_patreon and not dry_run and upload_missing_durable_id(
        record, "pathInitiateUploaded", "pathInitiatePostId"
    ):
        record["pathInitiateStatus"] = "AMBIGUOUS"
        record["lastError"] = "Path Initiate marked uploaded without a durable post ID. Fail closed."
        record["complete"] = False
        if record_path:
            save_workflow_record(record_path, record)
        plan["workflowStatus"] = "BLOCKED_AMBIGUOUS_PATH_INITIATE"
        plan["nextIncompleteStage"] = "upload_path_initiate"
        plan["sideEffects"] = side_effects
        plan["record"] = record
        plan["log"] = workflow_log_fields(plan, record)
        return plan

    if plan.get("wouldUploadInner") and allow_live_patreon and adapters.upload_inner and not upload_confirmed(
        record, "innerDiscipleUploaded", "innerDisciplePostId"
    ):
        try:
            result = adapters.upload_inner(novel, next_chapter, plan["innerDiscipleDate"]) or {}
        except Exception as exc:
            record["innerDiscipleStatus"] = "FAILURE"
            record["lastError"] = str(exc)
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_INNER_DISCIPLE"
            plan["nextIncompleteStage"] = "upload_inner_disciple"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            plan["log"] = workflow_log_fields(plan, record)
            return plan
        post_id = durable_remote_id(result.get("id"))
        if not post_id:
            record["innerDiscipleUploaded"] = False
            record["innerDiscipleStatus"] = "AMBIGUOUS"
            record["innerDisciplePostId"] = ""
            record["lastError"] = "Inner Disciple upload returned no durable post ID. Fail closed."
            record["complete"] = False
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_AMBIGUOUS_INNER_DISCIPLE"
            plan["nextIncompleteStage"] = "upload_inner_disciple"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            plan["log"] = workflow_log_fields(plan, record)
            return plan
        record["innerDiscipleUploaded"] = True
        record["innerDiscipleStatus"] = "SUCCESS"
        record["innerDisciplePostId"] = post_id
        record["patreonPostId"] = post_id
        side_effects.append("upload_inner")
        if record_path:
            save_workflow_record(record_path, record)

    if plan.get("wouldUploadPath") and allow_live_patreon and adapters.upload_path and not upload_confirmed(
        record, "pathInitiateUploaded", "pathInitiatePostId"
    ):
        try:
            result = adapters.upload_path(novel, next_chapter, plan["pathInitiateDate"]) or {}
        except Exception as exc:
            record["pathInitiateStatus"] = "FAILURE"
            record["lastError"] = str(exc)
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_PATH_INITIATE"
            plan["nextIncompleteStage"] = "upload_path_initiate"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            plan["log"] = workflow_log_fields(plan, record)
            return plan
        post_id = durable_remote_id(result.get("id"))
        if not post_id:
            record["pathInitiateUploaded"] = False
            record["pathInitiateStatus"] = "AMBIGUOUS"
            record["pathInitiatePostId"] = ""
            record["lastError"] = "Path Initiate upload returned no durable post ID. Fail closed."
            record["complete"] = False
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_AMBIGUOUS_PATH_INITIATE"
            plan["nextIncompleteStage"] = "upload_path_initiate"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            plan["log"] = workflow_log_fields(plan, record)
            return plan
        record["pathInitiateUploaded"] = True
        record["pathInitiateStatus"] = "SUCCESS"
        record["pathInitiatePostId"] = post_id
        side_effects.append("upload_path")
        if record_path:
            save_workflow_record(record_path, record)

    if plan.get("wouldUploadRoyalRoad") and allow_live_royal and adapters.upload_royal and not upload_confirmed(
        record, "royalRoadUploaded", "royalRoadChapterId"
    ):
        try:
            result = adapters.upload_royal(novel, next_chapter, plan["royalRoadDate"]) or {}
        except Exception as exc:
            record["royalRoadStatus"] = "FAILURE"
            record["lastError"] = str(exc)
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_ROYAL_ROAD"
            plan["nextIncompleteStage"] = "upload_royal_road"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            plan["log"] = workflow_log_fields(plan, record)
            return plan
        chapter_id = durable_remote_id(result.get("id"))
        if not chapter_id:
            record["royalRoadUploaded"] = False
            record["royalRoadStatus"] = "AMBIGUOUS"
            record["royalRoadChapterId"] = ""
            record["lastError"] = "Royal Road upload returned no durable chapter ID. Fail closed."
            record["complete"] = False
            if record_path:
                save_workflow_record(record_path, record)
            plan["workflowStatus"] = "BLOCKED_AMBIGUOUS_ROYAL_ROAD"
            plan["nextIncompleteStage"] = "upload_royal_road"
            plan["sideEffects"] = side_effects
            plan["record"] = record
            plan["log"] = workflow_log_fields(plan, record)
            return plan
        record["royalRoadUploaded"] = True
        record["royalRoadStatus"] = "SUCCESS"
        record["royalRoadChapterId"] = chapter_id
        if result.get("url"):
            record["royalRoadChapterUrl"] = str(result.get("url") or "").strip()
        record["royalRoadDate"] = plan.get("royalRoadDate")
        side_effects.append("upload_royal")
        if record_path:
            save_workflow_record(record_path, record)

    record["recorded"] = True
    record["validated"] = True
    record["generated"] = True
    save_done = bool(record.get("saved")) or adapters.save is None
    schedule_done = bool(record.get("scheduled")) or adapters.schedule is None
    patreon_done = (not allow_live_patreon) or (
        upload_confirmed(record, "innerDiscipleUploaded", "innerDisciplePostId")
        and upload_confirmed(record, "pathInitiateUploaded", "pathInitiatePostId")
    )
    royal_done = (not allow_live_royal) or upload_confirmed(record, "royalRoadUploaded", "royalRoadChapterId")
    record["complete"] = bool(save_done and schedule_done and patreon_done and royal_done)
    if record_path:
        save_workflow_record(record_path, record)
    plan["sideEffects"] = side_effects
    plan["record"] = record
    plan["workflowStatus"] = "COMPLETE" if record["complete"] else "PARTIAL"
    plan["nextIncompleteStage"] = next_incomplete_stage(record)
    plan["livePatreonAllowed"] = allow_live_patreon
    plan["liveRoyalRoadAllowed"] = allow_live_royal
    plan["log"] = workflow_log_fields(plan, record)
    return plan
