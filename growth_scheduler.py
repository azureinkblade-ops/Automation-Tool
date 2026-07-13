from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Iterable


NOVEL_ORDER = ("HA", "EN", "HP", "SF")
DEFAULT_WEIGHTS = {"HA": 2, "EN": 1, "HP": 1, "SF": 1}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
GOALS = ("Reach", "Comments", "Shares", "Followers", "Subscribers", "Traffic")
LINKTREE_URL = "https://linktr.ee/azureinkblade"

GOAL_CTAS = {
    "Reach": (
        "Share this with a fantasy reader who needs a new serial.",
        "Tag the reader who is always hunting for a new fantasy world.",
        "Pass this scene to someone who reads one more chapter at midnight.",
    ),
    "Comments": (
        "What would you do next? Tell me in the comments.",
        "Who made the right choice here? Leave your verdict.",
        "Predict the next consequence before the reveal lands.",
    ),
    "Shares": (
        "Send this scene to someone who loves progression fantasy.",
        "Share this with the friend who always chooses the dangerous path.",
        "Pass this chapter turn to your favorite serial-fiction reader.",
    ),
    "Followers": (
        "Follow Azure Inkblade so the next reveal finds you.",
        "Follow now and keep the next chapter in your feed.",
        "Stay with the arc. Follow for the next turning point.",
    ),
    "Subscribers": (
        "Subscribe for full chapter videos and the next release.",
        "Subscribe so the next narrated chapter does not get buried.",
        "Keep the story moving: subscribe for full chapters and shorts.",
    ),
    "Traffic": (
        f"Start reading, watch, or read ahead here: {LINKTREE_URL}",
        f"Choose your next Azure Inkblade story here: {LINKTREE_URL}",
        f"Find every novel, video, and early chapter here: {LINKTREE_URL}",
    ),
}

HOOK_TEMPLATES = (
    "The victory was real. So was the price.",
    "One choice changed the rules before anyone noticed.",
    "The safest path was the one nobody survived.",
    "Power answered, but it did not arrive alone.",
    "They expected surrender. They got a consequence.",
)


def monday_for(value: str | date | None = None) -> date:
    if isinstance(value, date):
        parsed = value
    elif str(value or "").strip():
        parsed = datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    else:
        parsed = date.today()
    return parsed - timedelta(days=parsed.weekday())


def normalize_weights(raw: dict[str, Any] | None) -> dict[str, int]:
    raw = raw if isinstance(raw, dict) else {}
    weights: dict[str, int] = {}
    for abbr in NOVEL_ORDER:
        try:
            value = int(raw.get(abbr, DEFAULT_WEIGHTS[abbr]))
        except (TypeError, ValueError):
            value = DEFAULT_WEIGHTS[abbr]
        weights[abbr] = max(0, min(10, value))
    if not any(weights.values()):
        return dict(DEFAULT_WEIGHTS)
    return weights


def _stable_rank(seed: str, value: str) -> str:
    return hashlib.sha256(f"{seed}|{value}".encode("utf-8")).hexdigest()


def cta_for_goal(goal: str, seed: str, history: Iterable[dict[str, Any]] = ()) -> str:
    variants = GOAL_CTAS.get(goal) or GOAL_CTAS["Traffic"]
    start = int(_stable_rank(seed, goal)[:8], 16) % len(variants)
    used = {normalize_fingerprint(row.get("cta")) for row in history if isinstance(row, dict)}
    for offset in range(len(variants)):
        candidate = variants[(start + offset) % len(variants)]
        if normalize_fingerprint(candidate) not in used:
            return candidate
    return variants[start]


def weighted_novel_slots(weights: dict[str, Any] | None, week_start: str | date | None = None) -> list[str]:
    """Allocate five deterministic slots while respecting weights and avoiding repeats."""
    normalized = normalize_weights(weights)
    if normalized == DEFAULT_WEIGHTS:
        return ["HA", "EN", "HP", "HA", "SF"]
    monday = monday_for(week_start)
    seed = monday.isoformat()
    total = sum(normalized.values()) or 1
    exact = {abbr: normalized[abbr] * len(WEEKDAYS) / total for abbr in NOVEL_ORDER}
    counts = {abbr: int(exact[abbr]) for abbr in NOVEL_ORDER}
    remaining = len(WEEKDAYS) - sum(counts.values())
    remainder_order = sorted(
        NOVEL_ORDER,
        key=lambda abbr: (-(exact[abbr] - counts[abbr]), _stable_rank(seed, abbr)),
    )
    for abbr in remainder_order[:remaining]:
        counts[abbr] += 1

    slots: list[str] = []
    while len(slots) < len(WEEKDAYS):
        candidates = [abbr for abbr in NOVEL_ORDER if counts[abbr] > 0]
        if not candidates:
            break
        non_repeat = [abbr for abbr in candidates if not slots or abbr != slots[-1]]
        pool = non_repeat or candidates
        choice = sorted(
            pool,
            key=lambda abbr: (-counts[abbr], -normalized[abbr], _stable_rank(f"{seed}|{len(slots)}", abbr)),
        )[0]
        slots.append(choice)
        counts[choice] -= 1
    return slots


def normalize_fingerprint(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def engagement_score(
    *,
    hook: str,
    cta: str,
    goal: str,
    platform_copy: dict[str, str],
    image_ref: str = "",
    history: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    history_rows = [row for row in history if isinstance(row, dict)]
    hook_key = normalize_fingerprint(hook)
    cta_key = normalize_fingerprint(cta)
    image_key = normalize_fingerprint(image_ref)
    repeated_hook = any(normalize_fingerprint(row.get("hook")) == hook_key for row in history_rows if hook_key)
    repeated_cta = any(normalize_fingerprint(row.get("cta")) == cta_key for row in history_rows if cta_key)
    repeated_image = any(normalize_fingerprint(row.get("imageRef")) == image_key for row in history_rows if image_key)

    hook_score = 22 if 35 <= len(hook.strip()) <= 110 else (15 if len(hook.strip()) >= 18 else 5)
    goal_score = 12 if goal in GOALS else 3
    cta_score = 17 if cta.strip() and any(token in cta.lower() for token in ("comment", "follow", "subscribe", "share", "send", "start", "read")) else 6
    platform_score = min(20, 4 * sum(bool(str(platform_copy.get(name) or "").strip()) for name in ("instagram", "tiktok", "x", "facebook", "youtube")))
    destination_score = 10 if LINKTREE_URL in " ".join(platform_copy.values()) or LINKTREE_URL in cta else 4
    diversity_score = 10 - (4 if repeated_hook else 0) - (3 if repeated_cta else 0) - (5 if repeated_image else 0)
    diversity_score = max(0, diversity_score)
    total = max(0, min(100, hook_score + goal_score + cta_score + platform_score + destination_score + diversity_score))
    warnings = []
    if repeated_hook:
        warnings.append("Hook repeats a recent planned or published post.")
    if repeated_cta:
        warnings.append("CTA repeats a recent planned or published post.")
    if repeated_image:
        warnings.append("Image repeats a recent planned or published post.")
    if total < 70:
        warnings.append("Predicted engagement is below the 70-point quality threshold.")
    return {
        "score": total,
        "classification": "strong" if total >= 85 else ("ready" if total >= 70 else "weak"),
        "weak": total < 70,
        "breakdown": {
            "hook": hook_score,
            "goal": goal_score,
            "cta": cta_score,
            "platformAdaptation": platform_score,
            "destination": destination_score,
            "diversity": diversity_score,
        },
        "diversity": {
            "repeatedHook": repeated_hook,
            "repeatedCta": repeated_cta,
            "repeatedImage": repeated_image,
            "warnings": warnings,
        },
    }


def _platform_copy(novel: str, hook: str, cta: str, goal: str) -> dict[str, str]:
    hub = LINKTREE_URL
    return {
        "instagram": f"{hook}\n\nStep into {novel}, where every victory leaves a mark and every choice carries forward. Feel the consequence, then choose what you would risk next.\n\n{cta}\n{hub}\n\n#AzureInkblade #WebNovel #ProgressionFantasy #FantasyReads",
        "tiktok": f"{hook} {cta} Read and watch: {hub} #BookTok #WebNovel #FantasyTok",
        "x": f"{hook}\n{cta}\n{hub}\n#AzureInkblade #WebNovel",
        "facebook": f"{hook}\n\nDiscover {novel} and follow the next turn in the story. Would you take the risk, or walk away? Tell me below.\n\n{cta}\n{hub}",
        "youtube": f"{hook}\n\nDiscover {novel}, an Azure Inkblade progression fantasy web novel built around escalating choices, character growth, and consequences. Watch the chapter story, then continue reading or find the next release through the official hub.\n\n{cta}\n{hub}\n\n#AzureInkblade #ProgressionFantasy #WebNovel #FantasyAudiobook",
    }


def build_weekly_growth_plan(
    *,
    week_start: str | date | None,
    weights: dict[str, Any] | None,
    novels: dict[str, str],
    chapter_context: dict[str, dict[str, Any]] | None = None,
    history: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    monday = monday_for(week_start)
    normalized_weights = normalize_weights(weights)
    chapter_context = chapter_context if isinstance(chapter_context, dict) else {}
    slots = weighted_novel_slots(normalized_weights, monday)
    history_rows = [row for row in history if isinstance(row, dict)]
    plan_rows: list[dict[str, Any]] = []
    local_history = list(history_rows)
    for index, (day_name, abbr) in enumerate(zip(WEEKDAYS, slots)):
        context = chapter_context.get(abbr) if isinstance(chapter_context.get(abbr), dict) else {}
        novel = str(novels.get(abbr) or abbr)
        chapter = context.get("chapter")
        title = str(context.get("title") or "").strip()
        goal = GOALS[index % len(GOALS)]
        template = HOOK_TEMPLATES[int(_stable_rank(monday.isoformat(), f"{abbr}|{index}")[:8], 16) % len(HOOK_TEMPLATES)]
        hook = f"{template} {novel}" if not title else f"{template} In {title}, {novel} changes direction."
        cta = cta_for_goal(goal, f"{monday.isoformat()}|{abbr}|{index}", local_history)
        platform_copy = _platform_copy(novel, hook, cta, goal)
        image_ref = str(context.get("imageRef") or "")
        quality = engagement_score(hook=hook, cta=cta, goal=goal, platform_copy=platform_copy, image_ref=image_ref, history=local_history)
        row = {
            "slot": index + 1,
            "day": day_name,
            "date": (monday + timedelta(days=index)).isoformat(),
            "type": "novel",
            "abbr": abbr,
            "novel": novel,
            "chapter": chapter,
            "chapterTitle": title,
            "engagementGoal": goal,
            "hook": hook,
            "cta": cta,
            "destination": LINKTREE_URL,
            "platformCopy": platform_copy,
            "imageRef": image_ref,
            "predictedEngagement": quality,
            "deliveryStatus": "blocked" if quality["weak"] else "ready",
        }
        plan_rows.append(row)
        local_history.append(row)

    saturday_hook = "Which Azure Inkblade world should get the next character or lore spotlight?"
    saturday_cta = cta_for_goal("Comments", f"{monday.isoformat()}|community", local_history)
    saturday_copy = _platform_copy("Azure Inkblade", saturday_hook, saturday_cta, "Comments")
    saturday_quality = engagement_score(hook=saturday_hook, cta=saturday_cta, goal="Comments", platform_copy=saturday_copy, history=local_history)
    plan_rows.append({
        "slot": 6, "day": "Saturday", "date": (monday + timedelta(days=5)).isoformat(), "type": "community_poll",
        "abbr": "", "novel": "Community", "chapter": None, "chapterTitle": "", "engagementGoal": "Comments",
        "hook": saturday_hook, "cta": saturday_cta, "destination": LINKTREE_URL, "platformCopy": saturday_copy,
        "imageRef": "", "predictedEngagement": saturday_quality, "deliveryStatus": "blocked" if saturday_quality["weak"] else "ready",
    })
    sunday_hook = "This week in Azure Inkblade: one choice, one cost, and four worlds still moving."
    sunday_cta = cta_for_goal("Traffic", f"{monday.isoformat()}|recap", local_history)
    sunday_copy = _platform_copy("Azure Inkblade", sunday_hook, sunday_cta, "Traffic")
    sunday_quality = engagement_score(hook=sunday_hook, cta=sunday_cta, goal="Traffic", platform_copy=sunday_copy, history=local_history)
    plan_rows.append({
        "slot": 7, "day": "Sunday", "date": (monday + timedelta(days=6)).isoformat(), "type": "recap",
        "abbr": "", "novel": "Weekly Recap", "chapter": None, "chapterTitle": "", "engagementGoal": "Traffic",
        "hook": sunday_hook, "cta": sunday_cta, "destination": LINKTREE_URL, "platformCopy": sunday_copy,
        "imageRef": "", "predictedEngagement": sunday_quality, "deliveryStatus": "blocked" if sunday_quality["weak"] else "ready",
    })
    repeated_hooks = [key for key, count in Counter(normalize_fingerprint(row["hook"]) for row in plan_rows).items() if key and count > 1]
    weak_rows = [row for row in plan_rows if row["predictedEngagement"]["weak"]]
    diversity_warning_rows = [
        row for row in plan_rows
        if any((row.get("predictedEngagement") or {}).get("diversity", {}).get(key) for key in ("repeatedHook", "repeatedCta", "repeatedImage"))
    ]
    plan_id = f"growth-{monday.isoformat()}"
    return {
        "schemaVersion": 1,
        "planId": plan_id,
        "weekStart": monday.isoformat(),
        "weekEnd": (monday + timedelta(days=6)).isoformat(),
        "weights": normalized_weights,
        "slots": plan_rows,
        "summary": {
            "totalSlots": len(plan_rows),
            "novelSlots": len([row for row in plan_rows if row["type"] == "novel"]),
            "communitySlots": 1,
            "recapSlots": 1,
            "weakSlots": len(weak_rows),
            "diversityWarnings": len(diversity_warning_rows),
            "averagePredictedScore": round(sum(row["predictedEngagement"]["score"] for row in plan_rows) / len(plan_rows), 1),
            "repeatedHooks": repeated_hooks,
            "ready": not weak_rows and not repeated_hooks and not diversity_warning_rows,
        },
    }
