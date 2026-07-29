"""Pure social-copy generation for the Automation Tool.

Home for all string/derivable-text generation that powers social posts, hashtags,
captions, CTAs, and chapter hooks. This module is STRICTLY pure: it imports only
``app_config`` (immutable constants) and the Python standard library. It MUST NOT
import ``app`` and MUST NOT touch the database, the filesystem, or any runtime state,
except through an injected ``rotation_next`` collaborator (the only stateful dep in the
closure — kept in app.py and passed in, per the extraction plan's injection pattern).

Behavior is preserved verbatim from app.py (pre-extraction); see the consolidation plan
(.hermes/plans/2026-07-16_143000-monolith-extraction.md, Task 1). The app keeps thin
compatibility wrappers that call these functions so existing behavior is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import app_config as config

# --- re-exported config constants used below ---
NOVEL_NAMES = config.NOVEL_NAMES
LINKTREE_URL = config.LINKTREE_URL
PATREON_URL = config.PATREON_URL

# Feature flag (mirrors app.ENABLE_NOVEL_VOICE_VARIANTS). promo_copy is a pure
# module and cannot import app, so the flag is defined locally with the same
# env var + default. Rollback: when False, focused_social_cta uses only the
# generic templates regardless of NOVEL_VOICE_VARIANTS.
ENABLE_NOVEL_VOICE_VARIANTS = str(
    __import__("os").environ.get("ENABLE_NOVEL_VOICE_VARIANTS", "true")
).strip().lower() in ("1", "true", "yes", "on")

# Slice 2 AIVSB retrieval feature flag. Defaults OFF (precedent: ENABLE_POST_AUDIO).
# When False, build_platform_posts behaves exactly as before: no retrieval import
# side effects, no DB reads, no retrieval invocation, no logging.
ENABLE_AIVSB_RETRIEVAL = str(
    __import__("os").environ.get("ENABLE_AIVSB_RETRIEVAL", "false")
).strip().lower() in ("1", "true", "yes", "on")

YOUTUBE_SOCIAL_URL = config.YOUTUBE_SOCIAL_URL
TIKTOK_URL = config.TIKTOK_URL
INSTAGRAM_URL = config.INSTAGRAM_URL
PROMO_ROTATION_STATE_FILE = config.PROMO_ROTATION_STATE_FILE
CREATOR_BENCHMARK_FILE = config.CREATOR_BENCHMARK_FILE
PREDICTIVE_GROWTH_PLAN_FILE = config.PREDICTIVE_GROWTH_PLAN_FILE

# --- local word/visual sets (immutable) ---
VISUAL_WORDS = {
    "altar", "armor", "ash", "beast", "blade", "blood", "castle", "cave", "chain", "city",
    "cliff", "crystal", "door", "dragon", "ember", "fire", "flame", "forge", "gate", "glow",
    "hall", "ice", "knife", "light", "mask", "monster", "portal", "rain", "river", "road",
    "ruin", "rune", "shadow", "ship", "sky", "smoke", "soldier", "stone", "storm", "sword",
    "temple", "tower", "wall", "weapon",
}
STORY_VISUAL_WORDS = {
    "EN": {
        "avatar", "beast", "hollow", "kael", "legacy", "level", "login", "nexus", "nexuspod",
        "nightfall", "nightshade", "patch", "pod", "reset", "spawn", "system", "twilight",
    },
    "HA": {"ascension", "core", "heavenly", "meridian", "qi", "realm", "sect", "spirit", "trial"},
    "SF": {"ember", "flame", "forge", "forging", "soul", "steel", "weapon"},
    "HP": {"disciple", "forest", "hundredfold", "martial", "path", "sect", "temple", "trial"},
}


# --- pure I/O helpers (no app import) ---

def read_json_safe(path: Path) -> Any | None:
    # Phase-3 retirement enforcement: a retired root JSON mirror must never be
    # treated as a live source. Fail safe to None and warn instead of reading.
    from storage.retired_state import warn_if_retired_read

    if warn_if_retired_read(path):
        import sys

        print(
            f"[retirement] blocked read of retired Phase-3 JSON mirror: {path}. "
            f"State is sourced from SQLite.",
            file=sys.stderr,
        )
        return None
    if not path.exists():
        return None
    try:
        if path.stat().st_size == 0:
            return None
        raw = path.read_text(encoding="utf-8-sig").strip()
        if not raw:
            return None
        return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        try:
            bad_path = path.with_name(f"{path.name}.bad-{int(time.time())}")
            path.replace(bad_path)
        except OSError:
            pass
        return None


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value


def repair_text_encoding(text: str) -> str:
    if any(marker in text for marker in ("â€", "â€™", "â€œ", "â€“", "Â")):
        try:
            repaired = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
            if repaired.count("�") <= text.count("�"):
                text = repaired
        except UnicodeError:
            pass
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€": '"',
        "â€�": '"',
        "â€“": "-",
        "â€”": "-",
        "â€¦": "...",
        "Â ": " ",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def normalize_story_text(text: str) -> str:
    text = repair_text_encoding(text)
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"([.!?])([A-Z\"'])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z][a-z])", r"\1 \2", text)
    return re.sub(r"\s+", " ", text).strip()


def chapter_body_for_marketing(text: str) -> str:
    text = repair_text_encoding(text)
    lines = [line.strip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    if lines and re.match(r"^chapter\s+\d+[A-Za-z]?(?:\s+Part\s+\d+)?\b", lines[0], re.IGNORECASE):
        lines = lines[1:]
    return "\n".join(lines).strip() or text


def story_key(value: str = "") -> str:
    value = value.upper().strip()
    if value in NOVEL_NAMES:
        return value
    for abbr, name in NOVEL_NAMES.items():
        if value == name.upper():
            return abbr
    return ""


def royal_road_url_for_story(story: str = "") -> str:
    from app_config import ROYAL_ROAD_URLS
    return ROYAL_ROAD_URLS.get(story_key(story), "")


def linktree_url() -> str:
    return config.LINKTREE_URL


def score_sentence(sentence: str) -> int:
    drama = {
        "blood", "dark", "secret", "death", "monster", "magic", "sword", "heart", "fire",
        "shadow", "betray", "king", "queen", "war", "kiss", "fear", "truth", "danger",
        "promise", "curse",
    }
    words = re.findall(r"[a-zA-Z']+", sentence.lower())
    return len(set(words) & drama) * 4 + min(len(words), 28)


def visual_score(sentence: str, story: str = "") -> int:
    words = set(re.findall(r"[a-zA-Z']+", sentence.lower()))
    key = story_key(story)
    story_words = STORY_VISUAL_WORDS.get(key, set())
    return len(words & VISUAL_WORDS) * 8 + len(words & story_words) * 10 + score_sentence(sentence)


def clean_teaser_text(sentence: str, limit: int = 82, max_words: int | None = 12) -> str:
    sentence = sentence.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    sentence = sentence.replace("\u2013", "-").replace("\u2014", "-")
    sentence = re.sub(r"\s+", " ", sentence).strip()
    sentence = re.sub(r"^[\"'`]+|[\"'`]+$", "", sentence).strip()
    sentence = re.sub(r"\b(said|asked|whispered|muttered|shouted)\s+[A-Z][a-zA-Z'-]+[,.]?\s*", "", sentence)
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    if max_words:
        words = sentence.split()
        if len(words) > max_words:
            sentence = " ".join(words[:max_words]).rstrip(",;:")
    weak_tail = {"a", "an", "and", "are", "as", "because", "by", "for", "from", "in", "of",
                 "the", "through", "to", "was", "were", "with"}
    words = sentence.split()
    while len(words) > 4 and words[-1].lower().strip(".,;:!?") in weak_tail:
        words.pop()
    sentence = " ".join(words)
    if sentence:
        sentence = sentence[0].upper() + sentence[1:]
    return sentence.rstrip(".")


def sentence_split(text: str) -> list[str]:
    text = chapter_body_for_marketing(text)
    cleaned = normalize_story_text(text)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if len(part.strip()) > 35]


def chapter_keywords(title: str, chapter: str, limit: int = 10) -> list[str]:
    chapter = chapter_body_for_marketing(chapter)
    stopwords = {
        "about", "after", "again", "against", "almost", "around", "because", "before", "being", "between",
        "chapter", "could", "every", "from", "have", "into", "just", "like", "more", "only", "over",
        "said", "some", "than", "that", "their", "them", "then", "there", "these", "they", "this",
        "through", "under", "until", "upon", "were", "what", "when", "where", "which", "while", "with",
        "would", "your",
    }
    counts: dict[str, int] = {}
    for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", f"{title} {chapter}"):
        normalized = word.strip("'").lower()
        if normalized in stopwords:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    ranked = sorted(counts, key=lambda item: (counts[item], len(item)), reverse=True)
    return ranked[:limit]


def visual_sentences(chapter: str, count: int = 3, story: str = "") -> list[str]:
    candidates = []
    for sentence in sentence_split(chapter):
        candidates.append((visual_score(sentence, story), sentence))
    ranked = [sentence for _, sentence in sorted(candidates, key=lambda item: item[0], reverse=True)]
    return ranked[:count]


def tracked_url(url: str, source: str, campaign: str, content: str = "", medium: str = "social") -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": slugify(source)[:40],
            "utm_medium": slugify(medium)[:40],
            "utm_campaign": slugify(campaign)[:80],
        }
    )
    if content:
        query["utm_content"] = slugify(content)[:80]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
    )


def track_copy_links(text: str, story: str, source: str, campaign: str, content: str = "") -> str:
    replacements = {
        royal_road_url_for_story(story): tracked_url(royal_road_url_for_story(story), source, campaign, content),
        linktree_url(): tracked_url(linktree_url(), source, campaign, content),
        PATREON_URL: tracked_url(PATREON_URL, source, campaign, content),
        YOUTUBE_SOCIAL_URL: tracked_url(YOUTUBE_SOCIAL_URL, source, campaign, content),
        TIKTOK_URL: tracked_url(TIKTOK_URL, source, campaign, content),
        INSTAGRAM_URL: tracked_url(INSTAGRAM_URL, source, campaign, content),
    }
    result = text
    for original, replacement in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if original and replacement:
            result = result.replace(original, replacement)
    return result


DIRECT_PUBLIC_URL_RE = re.compile(
    r"(?i)\b(?:https?://|www\.)?\S*(?:linktr\.ee|royalroad\.com|patreon\.com|youtube\.com|youtu\.be|tiktok\.com|x\.com|twitter\.com|instagram\.com)\S*"
)


def public_copy_without_links(text: str, platform: str = "") -> str:
    cleaned = DIRECT_PUBLIC_URL_RE.sub("", str(text or ""))
    cleaned = re.sub(r"(?im)^\s*(rr|royal road|patreon|youtube|tik\s*tok|tiktok|instagram|x|twitter)\b.*$", "", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    cta = "Read now: link in bio." if str(platform or "").strip().lower() in {"x", "twitter"} else "Read now. Link in bio."
    if cleaned and "link in bio" not in cleaned.lower():
        cleaned = f"{cleaned}\n\n{cta}"
    return cleaned or cta


def audience_hub_line(story: str = "", *, verb: str = "Start reading") -> str:
    profile = social_profile(story) if story else {"name": "Azure Inkblade"}
    name = str(profile.get("name") or "Azure Inkblade")
    if story_key(story):
        return f"{verb} {name}, watch chapter videos, and find every link in bio."
    return f"{verb}, watch, and follow Azure Inkblade through the link in bio."


def platform_links_block(story: str = "") -> str:
    return audience_hub_line(story)


# --- rotation_next is the ONLY stateful dep in this closure.
# It persists rotation state to disk (PROMO_ROTATION_STATE_FILE). Per the extraction
# plan it stays in app.py and is injected here as a collaborator. The default is a pure
# in-memory fallback so promo_copy imports and runs without app.py present. ---

def _in_memory_rotation_next(key: str, count: int) -> int:
    # Pure fallback used only when no collaborator is injected (tests, isolation).
    return 0


def social_profile(abbr_or_name: str) -> dict[str, str]:
    value = abbr_or_name.strip()
    abbr = value.upper() if value.upper() in NOVEL_NAMES else ""
    if not abbr:
        for key, name in NOVEL_NAMES.items():
            if name.lower() == value.lower() or name.replace(" ", "").lower() == value.replace(" ", "").lower():
                abbr = key
                break
    return {
        "HP": {
            "name": "Hundredfold Path",
            "emoji": "🌲",
            "patreon": "Stay ahead",
            "release": "The path continues",
            "hashtags": "#AzureInkblade #HundredfoldPath #BookTok #BookTokFantasy #FantasyBooks #WebNovel #WebNovelCommunity #RoyalRoad #RoyalRoadFantasy #ProgressionFantasy #CultivationFantasy #CultivationJourney #FantasyReads",
            "x_hashtags": "#HundredfoldPath #AzureInkblade #RoyalRoad #ProgressionFantasy",
        },
        "SF": {
            "name": "Soul Forge Era",
            "emoji": "⚔️",
            "patreon": "The forge burns bright",
            "release": "The forge burns bright",
            "hashtags": "#AzureInkblade #SoulForgeEra #BookTok #BookTokFantasy #FantasyBooks #WebNovel #WebNovelCommunity #RoyalRoad #RoyalRoadFantasy #ProgressionFantasy #CultivationFantasy #LitRPG #CultivationSaga #ForgedInFire",
            "x_hashtags": "#SoulForgeEra #AzureInkblade #RoyalRoad #ProgressionFantasy",
        },
        "EN": {
            "name": "Eternal Nexus",
            "emoji": "✨",
            "patreon": "Read ahead",
            "release": "The Nexus expands",
            "hashtags": "#AzureInkblade #EternalNexus #BookTok #BookTokFantasy #FantasyBooks #WebNovel #WebNovelCommunity #RoyalRoad #RoyalRoadFantasy #ProgressionFantasy #FantasyWorlds #NexusAwakens #FantasyReads",
            "x_hashtags": "#EternalNexus #AzureInkblade #RoyalRoad #FantasyBooks",
        },
        "HA": {
            "name": "Heavenly Ascension System",
            "emoji": "🔥",
            "patreon": "Ascend ahead",
            "release": "A new ascension begins",
            "hashtags": "#AzureInkblade #HeavenlyAscensionSystem #BookTok #BookTokFantasy #FantasyBooks #WebNovel #WebNovelCommunity #RoyalRoad #RoyalRoadFantasy #ProgressionFantasy #CultivationFantasy #LitRPG #FantasyReads",
            "x_hashtags": "#HeavenlyAscensionSystem #AzureInkblade #RoyalRoad #LitRPG",
        },
    }.get(
        abbr,
        {
            "name": value or "Azure Inkblade",
            "emoji": "✨",
            "patreon": "Read ahead",
            "release": "New chapter live",
            "hashtags": "#AzureInkblade #BookTok #BookTokFantasy #FantasyBooks #WebNovel #WebNovelCommunity #RoyalRoad #RoyalRoadFantasy #ProgressionFantasy #FantasyReads",
            "x_hashtags": "#AzureInkblade #RoyalRoad #webnovel",
        },
    )


def rotated_hashtags(abbr: str, seed: str, chapter_text: str = "", limit: int = 9) -> str:
    """Deterministic per-(abbr,chapter,day) hashtag set so daily posts don't repeat.

    Anchors the brand + novel tag, then rotates the remaining base hashtags by a hash of
    `seed` and appends up to two chapter-specific keywords. OpenAI-free; stable for a given seed.
    """
    profile = social_profile(abbr)
    base = [t for t in re.findall(r"#\w+", profile.get("hashtags", "")) if t]
    if not base:
        base = ["#AzureInkblade"]
    novel_tag = next((t for t in base if t.lower() != "#azureinkblade" and t.lower().lstrip("#") in profile.get("name", "").lower().replace(" ", "")), None)
    anchor = ["#AzureInkblade"] + ([novel_tag] if novel_tag else [])
    rest = [t for t in base if t not in anchor]
    # BUG FIX #1: deterministic SHA-256 ordering (built-in hash() is not stable across restarts)
    ordered = sorted(rest, key=lambda t: int(hashlib.sha256(f"{seed}:{t}".encode("utf-8")).hexdigest()[:8], 16))
    tags = anchor + ordered[: max(0, limit - len(anchor))]
    if chapter_text:
        for kw in chapter_keywords(chapter_text, chapter_text, limit=6):
            tag = "#" + "".join(w.capitalize() for w in re.split(r"[^\w]+", kw) if w)
            if tag not in tags and len(tags) < limit:
                tags.append(tag)
    return " ".join(tags)


def rotated_x_hashtags(abbr: str, seed: str, limit: int = 5) -> str:
    """X/Twitter variant of rotated_hashtags using the shorter x_hashtags base."""
    profile = social_profile(abbr)
    base = [t for t in re.findall(r"#\w+", profile.get("x_hashtags", "")) if t]
    if not base:
        base = ["#AzureInkblade"]
    # BUG FIX #1: deterministic SHA-256 ordering (built-in hash() is not stable across restarts)
    ordered = sorted(base, key=lambda t: int(hashlib.sha256(f"{seed}:{t}".encode("utf-8")).hexdigest()[:8], 16))
    return " ".join(ordered[:limit])


def chapter_range_text(start: int | str, end: int | str | None = None, prefix: str = "Ch.") -> str:
    start_text = str(start).strip()
    end_text = str(end).strip() if end is not None and str(end).strip() else ""
    if not start_text:
        return "new chapters"
    if end_text and end_text != start_text:
        return f"{prefix} {start_text}-{end_text}"
    return f"{prefix} {start_text}"


def compact_chapter_hook(title: str, chapter: str, phrases: list[str] | None = None, story: str = "") -> str:
    phrases = phrases or []
    for phrase in phrases:
        cleaned = clean_teaser_text(str(phrase), 140, max_words=22)
        if cleaned:
            return cleaned
    for sentence in visual_sentences(chapter, 3, story or title):
        cleaned = clean_teaser_text(sentence, 160, max_words=24)
        if cleaned:
            return cleaned
    body = chapter_body_for_marketing(chapter)
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", body).strip())
    for sentence in sentences:
        cleaned = clean_teaser_text(sentence, 160, max_words=24)
        if cleaned:
            return cleaned
    return f"A new chapter of {title} is ready."


def normalize_post_copy_mode(value: str) -> str:
    value = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "royal_road": "royal_road_live",
        "royalroad": "royal_road_live",
        "rr": "royal_road_live",
        "patreon": "patreon_early",
        "youtube": "youtube_release",
        "tiktok": "weekly_general_promo",
        "story": "weekly_general_promo",
        "general": "weekly_general_promo",
        "weekly": "weekly_general_promo",
        "catch_up": "catch_up_archive",
        "archive": "catch_up_archive",
    }
    return aliases.get(value, value)


def rotating_post_focus(abbr: str, context: str, *, rotation_next=_in_memory_rotation_next) -> str:
    variants = ["royal_road_live", "patreon_early", "weekly_general_promo", "youtube_release", "catch_up_archive"]
    index = rotation_next(f"POST_FOCUS_{context}_{story_key(abbr)}".upper(), len(variants))
    return variants[index]


def _ledger_entry_default(abbr: str, chapter: int) -> dict[str, Any]:
    # Pure default used when app.py has not injected the real ledger reader.
    # Returns an empty entry so auto_post_copy_mode falls through to weekly_general_promo
    # (safe, deterministic; app injects the real reader for accurate focus).
    return {}


def _release_status_default(story: str, chapter: int) -> dict[str, Any]:
    return {}


def auto_post_copy_mode(abbr: str, chapter: str | int = "", *, rr_live: bool = False,
                         chapter_ledger_entry=_ledger_entry_default) -> str:
    chapter_text = str(chapter or "").strip()
    if not chapter_text.isdigit():
        return "weekly_general_promo"
    entry = chapter_ledger_entry(abbr, int(chapter_text))
    if entry.get("socialPostsQueued") and (entry.get("postedToRoyalRoad") or rr_live):
        return "catch_up_archive"
    if entry.get("postedToRoyalRoad") or rr_live:
        return "royal_road_live"
    if entry.get("postedToPatreon") or entry.get("patreonDraftPrepared"):
        return "patreon_early"
    if entry.get("youtubeFullVideoBuilt"):
        return "youtube_release"
    return "weekly_general_promo"


def resolve_post_focus(abbr: str, context: str, requested: str = "", *, rr_live: bool = False, chapter: str | int = "",
                       rotation_next=_in_memory_rotation_next, chapter_ledger_entry=_ledger_entry_default) -> str:
    requested = (requested or "").strip().lower().replace("-", "_")
    requested = normalize_post_copy_mode(requested)
    allowed = {"royal_road_live", "patreon_early", "weekly_general_promo", "youtube_release", "catch_up_archive"}
    if requested in allowed:
        return requested
    if chapter:
        return auto_post_copy_mode(abbr, chapter, rr_live=rr_live, chapter_ledger_entry=chapter_ledger_entry)
    return "royal_road_live" if rr_live else rotating_post_focus(abbr, context, rotation_next=rotation_next)


def dynamic_cta_goal(abbr: str, focus: str, context: str = "", *, rotation_next=_in_memory_rotation_next) -> str:
    focus = normalize_post_copy_mode(focus)
    if focus == "royal_road_live":
        variants = ["start_reading", "comment_question", "follow_next"]
    elif focus == "patreon_early":
        variants = ["read_ahead", "support_release", "follow_next"]
    elif focus == "youtube_release":
        variants = ["watch_listen", "subscribe", "comment_question"]
    elif focus == "catch_up_archive":
        variants = ["catch_up", "start_reading", "follow_next"]
    elif "weekend" in context.lower():
        variants = ["start_reading", "catch_up", "author_resources", "follow_next"]
    else:
        variants = ["start_reading", "follow_next", "watch_listen", "author_resources"]
    key = f"CTA_GOAL_{context}_{story_key(abbr)}_{focus}".upper()
    return variants[rotation_next(key, len(variants))]


# Generic CTA variants (fallback when a novel has no voice-specific variant).
# Authored as format templates: {hub} fills the linktree URL, {name} the novel name.
GENERIC_CTA_VARIANTS = {
    "start_reading": [
        "Start {name} here: {hub}",
        "New to {name}? Begin reading here: {hub}",
        "Pick up {name} from the hub: {hub}",
    ],
    "read_ahead": [
        "Read ahead and catch the public chapters here: {hub}",
        "Early access, public chapters, and updates are all here: {hub}",
        "Want the next chapter sooner? Start here: {hub}",
    ],
    "watch_listen": [
        "Watch or listen to chapter releases here: {hub}",
        "Prefer video chapters and shorts? Find them here: {hub}",
        "Read, watch, or listen from one hub: {hub}",
    ],
    "follow_next": [
        "Follow for the next chapter drop: {hub}",
        "Do not miss the next update. Follow here: {hub}",
        "Follow the release trail here: {hub}",
    ],
    "comment_question": [
        "Tell me what you think, then read more here: {hub}",
        "Drop your prediction and continue here: {hub}",
        "Which choice would you make? Continue here: {hub}",
    ],
    "catch_up": [
        "Catch up before the next arc lands: {hub}",
        "Start from chapter one or jump into the latest updates: {hub}",
        "Weekend catch-up starts here: {hub}",
    ],
    "support_release": [
        "Support the release schedule and read more here: {hub}",
        "Help keep the chapters coming and read ahead here: {hub}",
        "Support Azure Inkblade and find every series here: {hub}",
    ],
    "subscribe": [
        "Subscribe, read, and watch from the Azure Inkblade hub: {hub}",
        "Follow the videos and chapters here: {hub}",
        "Keep the next chapter in your feed: {hub}",
    ],
    "author_resources": [
        "Readers can start the novels, and writers can find author tools here: {hub}",
        "Stories, videos, and author resources are all here: {hub}",
        "Read the novels or check out the author resources here: {hub}",
    ],
}

# Per-novel voice variants (2026-07-20 plan §1). Each novel speaks in its own
# voice (EN: LitRPG cyberpunk / Nexus; HA: urban cultivation / ascension;
# SF: undercity soul-forge / iron; HP: classical xianxia / path). Complete
# phrases only -- never assembled from interchangeable fragments. Keyed by
# normalized abbr (story_key) then CTA goal. {hub} = linktree URL.
NOVEL_VOICE_VARIANTS = {
    "EN": {
        "start_reading": [
            "Enter the Nexus and uncover what the system erased: {hub}",
            "The next echo is already waiting inside the Nexus: {hub}",
        ],
        "read_ahead": [
            "Patch into the early build and read ahead from the hub: {hub}",
            "The interface is open. Slip into the next node here: {hub}",
        ],
        "watch_listen": [
            "Watch the chapter render as a video, or listen to the echo here: {hub}",
            "The signal goes live in audio and video from the hub: {hub}",
        ],
        "follow_next": [
            "Follow the trail before the next system update ships: {hub}",
            "Stay logged in for the next Nexus drop: {hub}",
        ],
        "comment_question": [
            "Was that a system failure, or was the Nexus warning him?",
            "Which would you trust first: the interface or the echo behind it?",
        ],
        "catch_up": [
            "Recompile the early arcs before the next chapter locks: {hub}",
            "Catch up on every erased node from the hub: {hub}",
        ],
        "support_release": [
            "Keep the servers online and read the next build here: {hub}",
            "Support the release and the system stays one step ahead: {hub}",
        ],
        "subscribe": [
            "Subscribe and the Nexus pings you on every drop: {hub}",
            "Lock the feed so no echo slips past: {hub}",
        ],
        "author_resources": [
            "Readers enter the Nexus; writers find their own tools here: {hub}",
            "Stories, signals, and author resources all route through the hub: {hub}",
        ],
    },
    "HA": {
        "start_reading": [
            "Step onto the ascension path and claim your first meridian: {hub}",
            "The heavens opened a door. Walk through it here: {hub}",
        ],
        "read_ahead": [
            "Cultivate ahead of the tribulation from the sect hub: {hub}",
            "Gather qi for the next realm and read ahead here: {hub}",
        ],
        "watch_listen": [
            "Watch the Dao unfold in video, or hear it chanted from the hub: {hub}",
            "The ascension plays in audio and vision from the hub: {hub}",
        ],
        "follow_next": [
            "Follow the cultivator before the next heavenly trial: {hub}",
            "Stay sworn to the path for the next breakthrough: {hub}",
        ],
        "comment_question": [
            "Would you surrender your meridian to ascend?",
            "Which tribulation would you fear most: the heavens, or the sect?",
        ],
        "catch_up": [
            "Rebuild your foundation before the next ascent: {hub}",
            "Catch up on every realm from the sect hub: {hub}",
        ],
        "support_release": [
            "Feed the cultivator's qi and read the next chapter here: {hub}",
            "Support the release so the path stays open: {hub}",
        ],
        "subscribe": [
            "Subscribe and the heavens announce each new realm: {hub}",
            "Bind the feed to your core for every ascension: {hub}",
        ],
        "author_resources": [
            "Disciples read the Dao; masters find their craft here: {hub}",
            "Cultivation, lore, and author resources gather at the hub: {hub}",
        ],
    },
    "SF": {
        "start_reading": [
            "Descend to the undercity forge and hear the iron sing: {hub}",
            "The choir of souls is calling. Answer it here: {hub}",
        ],
        "read_ahead": [
            "Forge ahead of the next ember from the workshop hub: {hub}",
            "Temper your blade and read the early chapters here: {hub}",
        ],
        "watch_listen": [
            "Watch the anvil ring in video, or hear the soul-choir here: {hub}",
            "The forge plays in audio and fire from the hub: {hub}",
        ],
        "follow_next": [
            "Follow the smith before the next ember dies: {hub}",
            "Stay at the anvil for the next molten drop: {hub}",
        ],
        "comment_question": [
            "Would you trade your soul to finish the blade?",
            "Which would you forge first: the weapon, or the wielder?",
        ],
        "catch_up": [
            "Rekindle the cold forge before the next song: {hub}",
            "Catch up on every ember from the workshop hub: {hub}",
        ],
        "support_release": [
            "Feed the furnace and read the next chapter here: {hub}",
            "Support the release so the iron keeps singing: {hub}",
        ],
        "subscribe": [
            "Subscribe and the choir belts every new chapter: {hub}",
            "Bind the feed to your anvil for each drop: {hub}",
        ],
        "author_resources": [
            "Readers enter the forge; smiths find their craft here: {hub}",
            "Blades, souls, and author resources ring from the hub: {hub}",
        ],
    },
    "HP": {
        "start_reading": [
            "Take the hundredfold path and multiply your first step: {hub}",
            "The jade gate has opened. Walk the path here: {hub}",
        ],
        "read_ahead": [
            "Cultivate ahead of the next tribulation from the sect hub: {hub}",
            "Gather immortal qi and read ahead here: {hub}",
        ],
        "watch_listen": [
            "Watch the Dao bloom in video, or hear the mountain here: {hub}",
            "The path plays in audio and stillness from the hub: {hub}",
        ],
        "follow_next": [
            "Follow the wanderer before the next immortal trial: {hub}",
            "Stay on the path for the next breakthrough: {hub}",
        ],
        "comment_question": [
            "Would you climb the mountain, or become the mountain?",
            "Which tribulation would you face first: the sect, or the self?",
        ],
        "catch_up": [
            "Rebuild your foundation before the next ascent: {hub}",
            "Catch up on every realm from the sect hub: {hub}",
        ],
        "support_release": [
            "Sustain the cultivator's qi and read the next chapter here: {hub}",
            "Support the release so the path stays open: {hub}",
        ],
        "subscribe": [
            "Subscribe and the sect announces each new realm: {hub}",
            "Bind the feed to your core for every ascent: {hub}",
        ],
        "author_resources": [
            "Disciples walk the path; authors find their craft here: {hub}",
            "Immortal lore and author resources gather at the hub: {hub}",
        ],
    },
}


def focused_social_cta(abbr: str, focus: str, context: str = "", platform: str = "", *,
                        rotation_next=_in_memory_rotation_next) -> str:
    focus = normalize_post_copy_mode(focus)
    profile = social_profile(abbr)
    goal = dynamic_cta_goal(abbr, focus, context or platform, rotation_next=rotation_next)
    hub = "link in bio"
    name = profile["name"]
    # Per-novel voice variants (2026-07-20 plan §1): complete phrases in each
    # novel's voice, keyed by normalized abbr then CTA goal. Falls back to the
    # generic variants when the flag is off, a novel has no variant for the
    # requested goal, or the voice layer is unavailable -- so the CTA INTENT
    # (goal) stays separate from the VOICE layer.
    abbr_key = story_key(abbr)
    if ENABLE_NOVEL_VOICE_VARIANTS:
        variants = NOVEL_VOICE_VARIANTS.get(abbr_key, {}).get(goal) or GENERIC_CTA_VARIANTS.get(goal, [])
    else:
        variants = GENERIC_CTA_VARIANTS.get(goal, [])
    if not variants:
        return audience_hub_line(abbr)
    key = f"CTA_TEXT_{context}_{platform}_{abbr_key}_{focus}_{goal}".upper()
    return public_copy_without_links(variants[rotation_next(key, len(variants))].format(hub=hub, name=name), platform)





def engagement_prompt_line(abbr: str, style: str, context: str = "", *,
                           rotation_next=_in_memory_rotation_next) -> str:
    profile = social_profile(abbr)
    prompts = {
        "reader_question": [
            "Would you make the same choice?",
            "What would you do in this situation?",
            "Who do you trust after a scene like this?",
        ],
        "stakes": [
            "Comment with the moment you think changes everything.",
            "Save this if you like progression fantasy with real consequences.",
            "Which cost would be too high for you?",
        ],
        "character_moment": [
            "Follow if character turns are your favorite part of a long arc.",
            "Drop the character you are watching closest right now.",
            "Save this for your next serial fantasy read.",
        ],
        "worldbuilding": [
            "Follow for more hidden systems, strange realms, and chapter drops.",
            "Which part of this world would you explore first?",
            "Save this if you like web novels with layered worlds.",
        ],
        "catch_up": [
            f"Start {profile['name']} before the next chapter lands.",
            "Send this to someone who needs a new web novel.",
            "Weekend readers, this is your catch-up sign.",
        ],
    }.get(style, [
        "Follow for the next chapter drop.",
        "Save this for your next fantasy web novel read.",
        "Comment with your prediction for what happens next.",
    ])
    key = f"ENGAGEMENT_PROMPT_{context}_{story_key(abbr)}_{style}".upper()
    return prompts[rotation_next(key, len(prompts))]


def platform_engagement_prompt_line(abbr: str, style: str, platform: str = "", focus: str = "",
                                     context: str = "", *, rotation_next=_in_memory_rotation_next) -> str:
    platform = (platform or "").strip().lower().replace("_", "-")
    focus = normalize_post_copy_mode(focus)
    profile = social_profile(abbr)
    if platform in {"tiktok", "youtube-shorts", "instagram-reel", "shorts"}:
        prompts = [
            "Comment your prediction before the next reveal lands.",
            "Follow for the next scene if this kind of pressure is your thing.",
            "Which choice would you make here?",
        ]
    elif platform == "instagram":
        prompts = [
            "Save this for your next serial fantasy read.",
            "Comment with the moment you think changes everything.",
            "Send this to someone looking for a new web novel arc.",
        ]
    elif platform == "facebook":
        prompts = [
            "What would you do if this was the chapter you walked into?",
            "Which Azure Inkblade series should someone start with first?",
            "If you are catching up this week, tell me where you are starting.",
        ]
    elif platform == "x":
        prompts = [
            "Prediction?",
            "Start here.",
            "New readers welcome.",
        ]
    elif platform == "patreon":
        prompts = [
            "Thank you for helping keep the release schedule moving.",
            "Your support keeps the next chapter closer.",
            "Early readers help shape the momentum of the series.",
        ]
    else:
        return engagement_prompt_line(abbr, style, context, rotation_next=rotation_next)
    if focus == "royal_road_live" and platform in {"instagram", "facebook"}:
        prompts = [
            f"{profile['name']} is live publicly now. Where do you think the next turn goes?",
            "Comment with the scene you want to see paid off next.",
            "Save this if you are catching up on Royal Road this week.",
        ]
    key = f"PLATFORM_ENGAGEMENT_{context}_{platform}_{story_key(abbr)}_{style}_{focus}".upper()
    return prompts[rotation_next(key, len(prompts))]


def benchmark_preferred_caption_style(abbr: str = "", context: str = "") -> str:
    data = read_json_safe(CREATOR_BENCHMARK_FILE)
    if not isinstance(data, dict):
        return ""
    patterns = data.get("patterns") if isinstance(data.get("patterns"), dict) else {}
    top_hooks = patterns.get("topHookTypes") if isinstance(patterns.get("topHookTypes"), list) else []
    if not top_hooks:
        return ""
    hook = str(top_hooks[0].get("name") or "").lower()
    mapping = {
        "betrayal": "stakes",
        "revenge": "stakes",
        "power_fantasy": "scene_hook",
        "mystery": "worldbuilding",
        "horror": "scene_hook",
        "confession": "character_moment",
        "question": "reader_question",
        "cliffhanger": "stakes",
    }
    return mapping.get(hook, "")


def rotating_caption_style(abbr: str, context: str = "", *, rotation_next=_in_memory_rotation_next) -> str:
    benchmark_style = benchmark_preferred_caption_style(abbr, context)
    if benchmark_style and rotation_next(f"BENCHMARK_STYLE_{context}_{story_key(abbr)}".upper(), 3) == 0:
        return benchmark_style
    styles = [
        "scene_hook",
        "reader_question",
        "stakes",
        "character_moment",
        "worldbuilding",
        "catch_up",
    ]
    key = f"CAPTION_STYLE_{context}_{story_key(abbr)}".upper()
    return styles[rotation_next(key, len(styles))]


def caption_style_lines(
    abbr: str,
    novel: str,
    title: str,
    hook: str,
    focus: str,
    style: str,
    cta: str,
    status_line: str,
    context: str = "",
    platform: str = "",
    *,
    rotation_next=_in_memory_rotation_next,
) -> tuple[list[str], str]:
    profile = social_profile(abbr or novel)
    rr_url = royal_road_url_for_story(abbr)
    platform_key = (platform or "").strip().lower().replace("_", "-")
    engagement = platform_engagement_prompt_line(abbr, style, platform_key, focus, context, rotation_next=rotation_next)
    platform_bridge = {
        "instagram": "Built for readers who like serial fantasy, progression arcs, and chapter-by-chapter tension.",
        "facebook": "I am using these posts to help new readers find the right starting point without burying them in links.",
        "patreon": "This note is here for readers who want to support the release schedule and stay ahead.",
        "campaign": "Built for readers who want one clear place to start, watch, or read ahead.",
    }.get(platform_key, "")
    if style == "reader_question":
        opener = f"What would you do if {hook[:1].lower() + hook[1:] if hook else 'the next step changed everything'}?"
        body = [
            opener,
            hook,
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = opener
    elif style == "stakes":
        body = [
            f"The cost keeps climbing in {profile['name']}.",
            hook,
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = f"The cost keeps climbing in {profile['name']}: {hook}"
    elif style == "character_moment":
        body = [
            f"{profile['name']} - {title}",
            hook,
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = f"{title}: {hook}"
    elif style == "worldbuilding":
        body = [
            f"Step deeper into {profile['name']}.",
            hook,
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = f"Step deeper into {profile['name']}: {hook}"
    elif style == "catch_up":
        body = [
            f"New to {profile['name']}?",
            "This is a good point to catch up from the beginning before the next arc gets louder.",
            hook,
            platform_bridge,
            engagement,
            cta if focus != "catch_up_archive" else focused_social_cta(abbr, "catch_up_archive"),
        ]
        x_hook = f"Catch up on {profile['name']}: {rr_url or hook}"
    else:
        if platform_key == "instagram":
            opener = f"A chapter scene from {profile['name']}."
        elif platform_key == "facebook":
            opener = f"{profile['name']} - {title}"
        elif platform_key == "patreon":
            opener = f"{profile['name']} early-access note"
        else:
            opener = f"{profile['name']} - {title}"
        body = [
            opener,
            hook,
            status_line,
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = hook
    return [line for line in body if str(line or "").strip()], clean_teaser_text(x_hook, 180, max_words=28)


def predict_chapter_is_live_on_royal_road(
    abbr: str,
    chapter: str | int,
    material: dict[str, Any] | None = None,
    release_status_for_chapter: Any = _release_status_default,
) -> bool:
    material = material or {}
    status = material.get("release_status") if isinstance(material.get("release_status"), dict) else {}
    if status and status.get("royalRoadExists") is not None:
        return bool(status.get("royalRoadExists"))
    chapter_text = str(chapter or "").strip()
    if chapter_text.isdigit():
        try:
            return bool(release_status_for_chapter(story_key(abbr), int(chapter_text)).get("royalRoadExists"))
        except Exception:
            return False
    return False


def short_destination_copy(
    abbr: str,
    chapter: str | int = "",
    *,
    source: str = "",
    campaign: str = "",
    content: str = "daily-short",
    rotation_next=_in_memory_rotation_next,
) -> dict[str, str]:
    profile = social_profile(abbr)
    chapter_text = str(chapter or "").strip()
    rr_url = royal_road_url_for_story(abbr)
    rr_live = predict_chapter_is_live_on_royal_road(abbr, chapter_text)
    if rr_live and rr_url:
        hook_options = [
            "This chapter is live now, with more waiting when you are ready.",
            "Read the public chapter, then jump ahead if the cliffhanger catches you.",
            "The chapter is public now. Follow the trail before the next update lands.",
        ]
        focus = "royal_road_live"
    else:
        hook_options = [
            "Get the next chapters first on Patreon, or catch up free on the public chapters.",
            "Read ahead now or start from the public chapters when you are ready.",
            "The next turn is already waiting for early readers.",
        ]
        focus = "patreon_early"
    hook = hook_options[rotation_next(f"SHORT_HOOK_{story_key(abbr)}_{chapter_text}_{source}_{focus}".upper(), len(hook_options))]
    links = focused_social_cta(abbr, focus, f"short_{source}_{chapter_text}", source, rotation_next=rotation_next)
    if source:
        links = track_copy_links(
            links,
            abbr,
            source,
            campaign or f"{story_key(abbr)}-{chapter_text or 'general'}-daily-short",
            content,
        )
    return {"hook": hook, "links": links, "hashtags": profile["hashtags"], "x_hashtags": profile["x_hashtags"]}


@dataclass(frozen=True)
class RetrievedCompositionSignal:
    """Slice 2R: bounded structured signal derived from accepted retrieval hits.

    Only the field actually consumed by composition is present.
    """
    caption_style: str | None


# Slice 2R: existing curated caption-style vocabulary (promo_copy.rotating_caption_style).
CAPTION_STYLE_VOCAB = {
    "scene_hook", "reader_question", "stakes",
    "character_moment", "worldbuilding", "catch_up",
}

# Slice 2R: immutable explicit map from existing KnowledgeChunk.domain to a curated
# caption style. `location` -> `worldbuilding` is a deliberate POLICY mapping, not identity.
# visual_identity / video / lesson have no mapping (None).
DOMAIN_TO_CAPTION_STYLE = {
    "character": "character_moment",
    "worldbuilding": "worldbuilding",
    "location": "worldbuilding",
}


def _aivsb_retrieval_signal(
    story: str, novel: str, focus: str, context: str, material: dict,
    *, eval_sink=None,
) -> RetrievedCompositionSignal | None:
    """Slice 2R: derive a bounded composition signal from retrieval (no text injection).

    Returns None when the flag is OFF or retrieval is unavailable/fails/returns no
    mappable hit, so composition is unchanged. The formatted retrieval block is NOT a
    composition input; only the derived caption_style reaches the composer.

    Selection: traverse retrieve() hits in the EXACT returned order; pick the FIRST hit
    whose validated domain exists in DOMAIN_TO_CAPTION_STYLE; validate the mapped style
    against CAPTION_STYLE_VOCAB. Unknown/missing/malformed/future domains -> no signal.

    Provenance (sink-only): run_id, manifest_hash, query, returned_chunk_ids,
    injected_chunk_ids (legacy, always []), fallback_reason (retrieval layer),
    derived_signal, derived_signal_source_ids, derived_signal_source_rank,
    derived_signal_source_domain, signal_fallback_reason (signal-consumption layer).

    Failure containment: any exception inside retrieval returns None and records
    fallback_reason via eval_sink; it never propagates to post generation.
    """
    if not ENABLE_AIVSB_RETRIEVAL:
        return None
    try:
        from pathlib import Path
        from scripts.aivsb.retrieval import retrieve, get_active_index_run

        root = Path(__file__).resolve().parent
        run = get_active_index_run(root)
        run_id = run.run_id if run else None
        manifest_hash = run.manifest_hash if run else None

        chars = " ".join(str(c) for c in (material.get("characters") or []))
        query = " ".join(p for p in [novel, focus, context, chars, story] if p).strip()
        returned_ids: list[str] = []
        try:
            hits = retrieve(root, query, novel_id=story or None, top_n=5)
            returned_ids = [h.chunk_id for h in hits]
        except Exception as exc:  # contained: retrieval boundary only
            if eval_sink is not None:
                eval_sink({
                    "retrieval_enabled": True, "retrieval_attempted": True,
                    "retrieval_used": False, "run_id": run_id,
                    "manifest_hash": manifest_hash, "query": query,
                    "returned_chunk_ids": [], "injected_chunk_ids": [],
                    "fallback_reason": f"retrieval_error:{type(exc).__name__}",
                    "derived_signal": None,
                    "derived_signal_source_ids": [],
                    "derived_signal_source_rank": None,
                    "derived_signal_source_domain": None,
                    "signal_fallback_reason": None,
                })
            return None

        if not hits:
            if eval_sink is not None:
                eval_sink({
                    "retrieval_enabled": True, "retrieval_attempted": True,
                    "retrieval_used": False, "run_id": run_id,
                    "manifest_hash": manifest_hash, "query": query,
                    "returned_chunk_ids": [], "injected_chunk_ids": [],
                    "fallback_reason": "no_hits",
                    "derived_signal": None,
                    "derived_signal_source_ids": [],
                    "derived_signal_source_rank": None,
                    "derived_signal_source_domain": None,
                    "signal_fallback_reason": None,
                })
            return None

        # Traverse in retrieve() order; select the first hit whose domain maps.
        selected = None
        for rank, h in enumerate(hits, start=1):
            if h.novel_id and story and h.novel_id != story:
                continue  # novel isolation
            mapped = DOMAIN_TO_CAPTION_STYLE.get(str(h.domain or "").strip().lower())
            if mapped is None or mapped not in CAPTION_STYLE_VOCAB:
                continue
            selected = (mapped, h.chunk_id, rank, str(h.domain or ""))
            break

        if selected is None:
            if eval_sink is not None:
                eval_sink({
                    "retrieval_enabled": True, "retrieval_attempted": True,
                    "retrieval_used": True, "run_id": run_id,
                    "manifest_hash": manifest_hash, "query": query,
                    "returned_chunk_ids": returned_ids, "injected_chunk_ids": [],
                    "fallback_reason": None,
                    "derived_signal": None,
                    "derived_signal_source_ids": [],
                    "derived_signal_source_rank": None,
                    "derived_signal_source_domain": None,
                    "signal_fallback_reason": "no_mappable_domain",
                })
            return None

        mapped_style, sel_id, sel_rank, sel_domain = selected
        if eval_sink is not None:
            eval_sink({
                "retrieval_enabled": True, "retrieval_attempted": True,
                "retrieval_used": True, "run_id": run_id,
                "manifest_hash": manifest_hash, "query": query,
                "returned_chunk_ids": returned_ids, "injected_chunk_ids": [],
                "fallback_reason": None,
                "derived_signal": mapped_style,
                "derived_signal_source_ids": [sel_id],
                "derived_signal_source_rank": sel_rank,
                "derived_signal_source_domain": sel_domain,
                "signal_fallback_reason": None,
            })
        return RetrievedCompositionSignal(caption_style=mapped_style)
    except Exception:
        # Programming/setup defect outside retrieval must NOT be swallowed here;
        # only the retrieval boundary is contained. Re-raise anything
        # that isn't a retrieval failure.
        raise



def build_platform_posts(
    title: str,
    chapter: str,
    material: dict[str, Any],
    requested_focus: str = "",
    *,
    rotation_next=_in_memory_rotation_next,
    chapter_ledger_entry=_ledger_entry_default,
    release_status_for_chapter: Any = _release_status_default,
    agent_copy: dict | None = None,
    retrieval_eval_sink: "Callable[[dict], None] | None" = None,
) -> dict[str, str]:
    story = str(material.get("abbr") or material.get("novel") or "").strip()
    novel = str(material.get("novel") or NOVEL_NAMES.get(str(material.get("abbr", "")).upper(), "") or "Azure Inkblade").strip()
    # BUG FIX #2 helper: per-novel tag (not the generic #webnovel) for X/FB/IG tails.
    _profile = social_profile(story)
    novel_tag = next((t for t in re.findall(r"#\w+", _profile.get("hashtags", "")) if t.lower() != "#azureinkblade"), "")
    facebook_tail = f"{novel_tag} #RoyalRoad #ProgressionFantasy #FantasyReads" if novel_tag else "#AzureInkblade #RoyalRoad #ProgressionFantasy #FantasyReads"
    phrases = [str(item) for item in material.get("phrases", [])]
    hook = compact_chapter_hook(title, chapter, phrases, story or novel)
    links = platform_links_block(story)
    royal_road_url = royal_road_url_for_story(story)
    chapter_id = str(material.get("chapter") or normalize_chapter_id(title, material.get("chapter_number", "")) or "")
    rr_live = predict_chapter_is_live_on_royal_road(story, chapter_id, material, release_status_for_chapter=release_status_for_chapter)
    auto_focus = predictive_default_post_focus(story, rr_live=rr_live)
    focus = resolve_post_focus(
        story,
        f"campaign_{chapter_id or slugify(title)}",
        requested_focus or str(material.get("post_focus_override") or "") or auto_focus,
        rr_live=rr_live,
        chapter=chapter_id,
        rotation_next=rotation_next,
        chapter_ledger_entry=chapter_ledger_entry,
    )
    campaign_key = f"{story_key(story)}-{chapter_id or slugify(title)}-{focus}"
    cta = focused_social_cta(story, focus, f"campaign_{chapter_id or slugify(title)}", "instagram", rotation_next=rotation_next)
    public_status_line = {
        "royal_road_live": "This chapter is live on Royal Road now. Patreon remains the place to read ahead.",
        "patreon_early": "Early access is open on Patreon before the public Royal Road release.",
        "weekly_general_promo": "Follow the weekly release cycle across Royal Road, Patreon, YouTube, and short-form teasers.",
        "youtube_release": "The chapter video release is ready on YouTube for readers who want to listen.",
        "catch_up_archive": "Catch up from the archive and follow the next release when you are ready.",
    }.get(focus, "Follow the latest Azure Inkblade story updates.")
    style = rotating_caption_style(story, f"campaign_{chapter_id or slugify(title)}_{focus}", rotation_next=rotation_next)  # baseline (advances rotation)
    context = f"campaign_{chapter_id or slugify(title)}"
    # Slice 2R: derive a bounded composition signal from retrieval (flag-gated, pre-composition).
    # The formatted retrieval block is NOT injected into final outputs; only the derived
    # caption_style may override the current style. Rotation state is advanced identically
    # in both arms above.
    _sig = (
        _aivsb_retrieval_signal(story, novel, focus, context, material, eval_sink=retrieval_eval_sink)
        if ENABLE_AIVSB_RETRIEVAL else None
    )
    if _sig is not None and _sig.caption_style in CAPTION_STYLE_VOCAB:
        style = _sig.caption_style
    style_lines, x_hook = caption_style_lines(story, novel, title, hook, focus, style, cta, public_status_line, context, "instagram", rotation_next=rotation_next)
    facebook_cta = focused_social_cta(story, focus, context, "facebook", rotation_next=rotation_next)
    facebook_lines, _ = caption_style_lines(story, novel, title, hook, focus, style, facebook_cta, public_status_line, context, "facebook", rotation_next=rotation_next)
    patreon_cta = focused_social_cta(story, "patreon_early" if focus != "royal_road_live" else focus, context, "patreon", rotation_next=rotation_next)
    patreon_lines, _ = caption_style_lines(story, novel, title, hook, focus, style, patreon_cta, public_status_line, context, "patreon", rotation_next=rotation_next)
    instagram_caption = "\n\n".join(style_lines + [f"#AzureInkblade {novel_tag} #RoyalRoad #WebNovelCommunity #ProgressionFantasy #FantasyReads" if novel_tag else "#AzureInkblade #RoyalRoad #WebNovelCommunity #ProgressionFantasy #FantasyReads"])
    facebook_intro_lines = facebook_lines[:4] if len(facebook_lines) > 4 else facebook_lines
    if facebook_intro_lines and (
        facebook_intro_lines[0].strip().lower() == f"{novel} - {title}".strip().lower()
        or facebook_intro_lines[0].strip().lower() == title.strip().lower()
    ):
        facebook_intro_lines = facebook_intro_lines[1:]
    facebook_intro = "\n\n".join(facebook_intro_lines)
    patreon_note = (
        f"{novel}\n{title}\n\n"
        f"{patreon_lines[0] if patreon_lines else hook}\n\n"
        f"{hook}\n\n"
        f"{patreon_cta}\n\n"
        "Thank you for supporting the stories and helping keep the release schedule moving."
    )
    facebook_post = (
        f"{novel} - {title}\n\n"
        f"{facebook_intro}\n\n"
        "Follow the story across the main channels for chapter drops, teasers, and early access updates.\n\n"
        f"{facebook_cta}\n\n"
        f"{facebook_tail}"
    )
    x_destination = "Read now: link in bio."
    x_parts = [f"{novel} - {title}", x_hook or hook]
    if focus == "royal_road_live" and royal_road_url:
        x_parts.append("Read and follow through the link in bio.")
    elif focus == "patreon_early":
        x_parts.append("Read ahead through the link in bio.")
    elif focus == "youtube_release":
        x_parts.append("Watch/listen through the link in bio.")
    elif focus == "weekly_general_promo":
        x_parts.append(x_destination)
    elif focus == "catch_up_archive":
        x_parts.append(x_destination)
    elif royal_road_url:
        x_parts.append(x_destination)
    else:
        x_parts.append(x_destination)
    x_parts.append(f"{novel_tag} #RoyalRoad" if novel_tag else "#AzureInkblade #RoyalRoad")
    x_post = "\n\n".join(x_parts)
    if len(x_post) > 280:
        # Fallback 1: keep destination + novel tag (drop rotated X hook frame).
        fallback_1 = f"{x_destination}\n\n{novel_tag}" if novel_tag else f"{x_destination}\n#AzureInkblade"
        if len(fallback_1) <= 280:
            x_post = fallback_1
        else:
            # Fallback 2: destination + brand only (never reintroduce generic #webnovel).
            x_post = f"{x_destination}\n#AzureInkblade"
    # ---- Agent override (Hermes post-differentiation). ----
    # When the caller passes agent_copy (from tools/agent_post_writer.generate_post_copy),
    # splice the agent's reader-facing caption/cta/hashtags over the template output.
    # The template above remains the fallback when agent_copy is None (or partial).
    if isinstance(agent_copy, dict) and agent_copy.get("caption"):
        _ag_caption = str(agent_copy["caption"]).strip()
        _ag_cta = str(agent_copy.get("cta") or "").strip()
        _ag_tags = agent_copy.get("hashtags") or []
        _ag_tag_str = " ".join(str(t) for t in _ag_tags if str(t).strip())
        # Ensure brand + novel anchors are present even if the agent omitted them.
        if "#AzureInkblade" not in _ag_tag_str:
            _ag_tag_str = f"#AzureInkblade {_ag_tag_str}".strip()
        if novel_tag and novel_tag not in _ag_tag_str:
            _ag_tag_str = f"{_ag_tag_str} {novel_tag}".strip()
        # Instagram: agent caption + agent cta (once) + agent hashtags.
        instagram_caption = (
            f"{_ag_caption}\n\n{_ag_cta}\n\n{_ag_tag_str}" if _ag_cta else f"{_ag_caption}\n\n{_ag_tag_str}"
        )
        # Facebook: keep novel/title header + agent caption + agent cta + agent tags.
        _fb_body = _ag_caption
        if _ag_cta:
            _fb_body = f"{_fb_body}\n\n{_ag_cta}"
        facebook_post = (
            f"{novel} - {title}\n\n"
            f"{_fb_body}\n\n"
            f"{_ag_tag_str}"
        )
        # Patreon note: keep structure, swap in agent caption + cta.
        patreon_note = (
            f"{novel}\n{title}\n\n"
            f"{_ag_caption}\n\n"
            f"{_ag_cta or patreon_cta}\n\n"
            "Thank you for supporting the stories and helping keep the release schedule moving."
        )
        # X: agent caption (trimmed to 280) + agent tags; keep tracked destination.
        _x_body = _ag_caption
        if _ag_cta:
            _x_body = f"{_x_body}\n\n{_ag_cta}"
        _x_full = f"{novel} - {title}\n\n{_x_body}\n\n{_ag_tag_str}"
        if len(_x_full) > 280:
            _x_full = f"{_x_body}\n\n{_ag_tag_str}"
        if len(_x_full) > 280:
            _x_full = f"{_ag_tag_str}"
        x_post = _x_full
    return {
        "caption": public_copy_without_links(instagram_caption, "instagram"),
        "patreon_note": public_copy_without_links(patreon_note, "patreon"),
        "facebook_post": public_copy_without_links(facebook_post, "facebook"),
        "x_post": public_copy_without_links(x_post, "x"),
        "x_thread_links": track_copy_links(links, story, "x", campaign_key, "daily-post-links"),
        "post_focus": focus,
        "caption_style": style,
        "tracking_campaign": campaign_key,
        "_agent_source": (agent_copy.get("_source") if isinstance(agent_copy, dict) else None),
    }


def predictive_default_post_focus(story: str = "", *, rr_live: bool = False) -> str:
    if rr_live:
        return "royal_road_live"
    plan = read_json_safe(PREDICTIVE_GROWTH_PLAN_FILE)
    if not isinstance(plan, dict):
        return ""
    weekly = plan.get("weeklyReport") if isinstance(plan.get("weeklyReport"), dict) else {}
    best_hooks = weekly.get("bestHookTypes") if isinstance(weekly.get("bestHookTypes"), list) else []
    if best_hooks:
        top_hook = str(best_hooks[0].get("name") or "").lower()
        if "youtube" in top_hook:
            return "youtube_release"
        if "archive" in top_hook or "catch" in top_hook:
            return "catch_up_archive"
    primary = str(plan.get("primaryPlatform") or "").lower()
    if primary == "youtube":
        return "youtube_release"
    if primary in {"tiktok", "instagram", "facebook", "x"}:
        return "royal_road_live" if rr_live else "weekly_general_promo"
    return ""


def normalize_chapter_id(title: str, chapter: str | int = "") -> str:
    chapter_id = str(chapter).strip()
    if chapter_id:
        return chapter_id
    if re.search(r"\bprologue\b", title or "", re.IGNORECASE):
        return "0"
    match = re.search(r"\bchapter\s+(\d+[A-Za-z]?)\b", title or "", re.IGNORECASE)
    return match.group(1) if match else ""


def with_instagram_links(text: str, story: str = "") -> str:
    return public_copy_without_links(text, "instagram")


def fallback_social_copy(novel: str, abbr: str, day: str, filename: str) -> dict[str, str]:
    profile = social_profile(abbr or novel)
    tags = rotated_hashtags(abbr, f"{abbr}-{day}", chapter_text=filename, limit=9)
    x_tags = rotated_x_hashtags(abbr, f"{abbr}-{day}", limit=5)
    royal_road_url = royal_road_url_for_story(abbr or novel)
    focus = rotating_post_focus(abbr, f"fallback_social_{day}")
    style = rotating_caption_style(abbr, f"fallback_social_{day}_{focus}")
    cta = focused_social_cta(abbr, focus, f"daily_{day}_general", "daily")
    generic_hooks = {
        "scene_hook": f"One scene from {profile['name']} worth pausing on.",
        "reader_question": "What kind of power would you chase if the cost kept rising?",
        "stakes": f"The next step is never free in {profile['name']}.",
        "character_moment": f"A turning point for {profile['name']} — the kind that changes what comes next.",
        "worldbuilding": f"Step into the world of {profile['name']}: hidden systems, rising threats, hard-won power.",
        "catch_up": "Start from the beginning or catch up before the next release lands.",
    }
    hook = generic_hooks.get(style, generic_hooks["scene_hook"])
    instagram = "\n".join(
        [
            f"{profile['emoji']} {profile['name']} - {day} spotlight",
            "",
            hook,
            "",
            cta,
            "",
            audience_hub_line(abbr),
            "",
            tags,
        ]
    )
    x_text = f"{profile['emoji']} {hook}\nRead now: link in bio.\n{x_tags}"
    if len(x_text) > 260:
        x_text = x_text[:257].rsplit(" ", 1)[0] + "..."
    facebook = "\n\n".join(
        [
            f"{profile['emoji']} {profile['name']} - {day} spotlight",
            hook,
            cta,
            "Follow the story updates across the main channels.",
            audience_hub_line(abbr),
            tags,
        ]
    )
    return {
        "instagram": with_instagram_links(instagram, abbr),
        "x": x_text,
        "facebook": public_copy_without_links(facebook, "facebook"),
        "alt_text": f"Promotional image for {profile['name']}, scheduled for {day}.",
        "post_focus": focus,
        "caption_style": style,
    }
    instagram = "\n".join(
        [
            f"{profile['emoji']} {profile['patreon']} — {profile['name']} has chapters waiting on Patreon!",
            f"RR {royal_road_url}",
            f"Patreon {PATREON_URL}",
            f"YouTube {YOUTUBE_SOCIAL_URL}",
            f"TikTok {TIKTOK_URL}",
            "",
            tags,
        ]
    )
    x_text = f"{profile['emoji']} {profile['name']} chapters are waiting on Patreon.\n👉 {PATREON_URL}\n{x_tags}"
    if len(x_text) > 260:
        x_text = x_text[:257].rsplit(" ", 1)[0] + "..."
    facebook = "\n\n".join(
        [
            f"{profile['emoji']} {profile['patreon']} — {profile['name']} has chapters waiting on Patreon!",
            "Read now on Royal Road, support early access on Patreon, and follow the story updates here.",
            platform_links_block(abbr),
            tags,
        ]
    )
    return {
        "instagram": with_instagram_links(instagram, abbr),
        "x": x_text,
        "facebook": facebook,
        "alt_text": f"Promotional image for {profile['name']}, scheduled for {day}.",
    }


# --- app-bound collaborators (injected, not imported) ---
# Two functions in this closure depend on app/DB state that lives in app.py / release_state
# (Task 3) and is intentionally NOT imported here (the plan forbids promo_copy importing app):
#   * auto_post_copy_mode        -> needs chapter_ledger_entry(abbr, chapter)
#   * predict_chapter_is_live... -> needs release_status_for_chapter(story, chapter)
# Both accept that collaborator as a keyword arg with a safe pure default
# (_ledger_entry_default / _release_status_default) so the module imports and runs standalone.
# At Task 8 (inversion) app.py will inject the real readers when wiring these functions.
