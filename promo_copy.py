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

import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import app_config as config

# --- re-exported config constants used below ---
NOVEL_NAMES = config.NOVEL_NAMES
LINKTREE_URL = config.LINKTREE_URL
PATREON_URL = config.PATREON_URL
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


def audience_hub_line(story: str = "", *, verb: str = "Start reading") -> str:
    profile = social_profile(story) if story else {"name": "Azure Inkblade"}
    name = str(profile.get("name") or "Azure Inkblade")
    if story_key(story):
        return f"{verb} {name}, watch chapter videos, and find all links: {linktree_url()}"
    return f"{verb}, watch, and follow Azure Inkblade: {linktree_url()}"


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
    ordered = sorted(rest, key=lambda t: hash(f"{seed}:{t}"))
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
    ordered = sorted(base, key=lambda t: hash(f"{seed}:{t}"))
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


def focused_social_cta(abbr: str, focus: str, context: str = "", platform: str = "", *,
                        rotation_next=_in_memory_rotation_next) -> str:
    focus = normalize_post_copy_mode(focus)
    profile = social_profile(abbr)
    goal = dynamic_cta_goal(abbr, focus, context or platform, rotation_next=rotation_next)
    hub = linktree_url()
    name = profile["name"]
    variants = {
        "start_reading": [
            f"Start {name} here: {hub}",
            f"New to {name}? Begin reading here: {hub}",
            f"Pick up {name} from the hub: {hub}",
        ],
        "read_ahead": [
            f"Read ahead and catch the public chapters here: {hub}",
            f"Early access, public chapters, and updates are all here: {hub}",
            f"Want the next chapter sooner? Start here: {hub}",
        ],
        "watch_listen": [
            f"Watch or listen to chapter releases here: {hub}",
            f"Prefer video chapters and shorts? Find them here: {hub}",
            f"Read, watch, or listen from one hub: {hub}",
        ],
        "follow_next": [
            f"Follow for the next chapter drop: {hub}",
            f"Do not miss the next update. Follow here: {hub}",
            f"Follow the release trail here: {hub}",
        ],
        "comment_question": [
            f"Tell me what you think, then read more here: {hub}",
            f"Drop your prediction and continue here: {hub}",
            f"Which choice would you make? Continue here: {hub}",
        ],
        "catch_up": [
            f"Catch up before the next arc lands: {hub}",
            f"Start from chapter one or jump into the latest updates: {hub}",
            f"Weekend catch-up starts here: {hub}",
        ],
        "support_release": [
            f"Support the release schedule and read more here: {hub}",
            f"Help keep the chapters coming and read ahead here: {hub}",
            f"Support Azure Inkblade and find every series here: {hub}",
        ],
        "subscribe": [
            f"Subscribe, read, and watch from the Azure Inkblade hub: {hub}",
            f"Follow the videos and chapters here: {hub}",
            f"Keep the next chapter in your feed: {hub}",
        ],
        "author_resources": [
            f"Readers can start the novels, and writers can find author tools here: {hub}",
            f"Stories, videos, and author resources are all here: {hub}",
            f"Read the novels or check out the author resources here: {hub}",
        ],
    }.get(goal, [])
    if not variants:
        return audience_hub_line(abbr)
    key = f"CTA_TEXT_{context}_{platform}_{story_key(abbr)}_{focus}_{goal}".upper()
    return variants[rotation_next(key, len(variants))]


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
            f"{profile['name']} turns that pressure into the next chapter.",
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = opener
    elif style == "stakes":
        body = [
            f"The cost keeps climbing in {profile['name']}.",
            hook,
            "This chapter is about pressure, consequence, and the next choice that cannot be taken back.",
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = f"The cost keeps climbing in {profile['name']}: {hook}"
    elif style == "character_moment":
        body = [
            f"{profile['name']} - {title}",
            hook,
            "A character moment sits at the center of this update, with the larger arc tightening around it.",
            platform_bridge,
            engagement,
            cta,
        ]
        x_hook = f"{title}: {hook}"
    elif style == "worldbuilding":
        body = [
            f"Step deeper into {profile['name']}.",
            hook,
            "The world is widening, and the next reveal changes what the path ahead looks like.",
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
            opener = f"This {profile['name']} update is built around one pressure point."
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


def build_platform_posts(
    title: str,
    chapter: str,
    material: dict[str, Any],
    requested_focus: str = "",
    *,
    rotation_next=_in_memory_rotation_next,
    chapter_ledger_entry=_ledger_entry_default,
    release_status_for_chapter: Any = _release_status_default,
) -> dict[str, str]:
    story = str(material.get("abbr") or material.get("novel") or "").strip()
    novel = str(material.get("novel") or NOVEL_NAMES.get(str(material.get("abbr", "")).upper(), "") or "Azure Inkblade").strip()
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
    style = rotating_caption_style(story, f"campaign_{chapter_id or slugify(title)}_{focus}", rotation_next=rotation_next)
    context = f"campaign_{chapter_id or slugify(title)}"
    style_lines, x_hook = caption_style_lines(story, novel, title, hook, focus, style, cta, public_status_line, context, "instagram", rotation_next=rotation_next)
    facebook_cta = focused_social_cta(story, focus, context, "facebook", rotation_next=rotation_next)
    facebook_lines, _ = caption_style_lines(story, novel, title, hook, focus, style, facebook_cta, public_status_line, context, "facebook", rotation_next=rotation_next)
    patreon_cta = focused_social_cta(story, "patreon_early" if focus != "royal_road_live" else focus, context, "patreon", rotation_next=rotation_next)
    patreon_lines, _ = caption_style_lines(story, novel, title, hook, focus, style, patreon_cta, public_status_line, context, "patreon", rotation_next=rotation_next)
    instagram_caption = "\n\n".join(style_lines + ["#AzureInkblade #RoyalRoad #WebNovelCommunity #ProgressionFantasy #FantasyReads"])
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
        "#webnovel #royalroad #serialfiction #progressionfantasy #indieauthor"
    )
    x_destination = track_copy_links(linktree_url(), story, "x", campaign_key, "daily-post")
    x_parts = [f"{novel} - {title}", x_hook or hook]
    if focus == "royal_road_live" and royal_road_url:
        x_parts.append(track_copy_links(f"Read and follow: {linktree_url()}", story, "x", campaign_key, "daily-post"))
    elif focus == "patreon_early":
        x_parts.append(track_copy_links(f"Read ahead: {linktree_url()}", story, "x", campaign_key, "daily-post"))
    elif focus == "youtube_release":
        x_parts.append(track_copy_links(f"Watch/listen: {linktree_url()}", story, "x", campaign_key, "daily-post"))
    elif focus == "weekly_general_promo":
        x_parts.append(x_destination)
    elif focus == "catch_up_archive":
        x_parts.append(x_destination)
    elif royal_road_url:
        x_parts.append(x_destination)
    else:
        x_parts.append(x_destination)
    x_parts.append("#webnovel #RoyalRoad")
    x_post = "\n\n".join(x_parts)
    if len(x_post) > 275:
        available = max(24, 275 - len(x_destination) - len("\n\n#webnovel") - 2)
        compact_hook = clean_teaser_text(hook, available, max_words=18)
        x_post = f"{compact_hook}\n\n{x_destination}\n\n#webnovel"
    if len(x_post) > 275:
        x_post = f"{x_destination}\n#webnovel"
    return {
        "caption": track_copy_links(instagram_caption, story, "instagram", campaign_key, "daily-post"),
        "patreon_note": track_copy_links(patreon_note, story, "patreon", campaign_key, "daily-post"),
        "facebook_post": track_copy_links(facebook_post, story, "facebook", campaign_key, "daily-post"),
        "x_post": x_post,
        "x_thread_links": track_copy_links(links, story, "x", campaign_key, "daily-post-links"),
        "post_focus": focus,
        "caption_style": style,
        "tracking_campaign": campaign_key,
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
    text = text.strip()
    if linktree_url() in text:
        return text
    footer = platform_links_block(story)
    return f"{text}\n\n{footer}" if text else footer


def fallback_social_copy(novel: str, abbr: str, day: str, filename: str) -> dict[str, str]:
    profile = social_profile(abbr or novel)
    tags = rotated_hashtags(abbr, f"{abbr}-{day}", chapter_text=filename, limit=9)
    x_tags = rotated_x_hashtags(abbr, f"{abbr}-{day}", limit=5)
    royal_road_url = royal_road_url_for_story(abbr or novel)
    focus = rotating_post_focus(abbr, f"fallback_social_{day}")
    style = rotating_caption_style(abbr, f"fallback_social_{day}_{focus}")
    cta = focused_social_cta(abbr, focus, f"daily_{day}_general", "daily")
    generic_hooks = {
        "scene_hook": f"{profile['name']} is moving into the next pressure point.",
        "reader_question": "What kind of power would you chase if the cost kept rising?",
        "stakes": f"The next step is never free in {profile['name']}.",
        "character_moment": "Every arc has a moment where the path starts choosing back.",
        "worldbuilding": "Step into a world of hidden systems, rising threats, and hard-won power.",
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
            platform_links_block(abbr),
            "",
            tags,
        ]
    )
    x_link = linktree_url()
    x_text = f"{profile['emoji']} {hook}\n{x_link}\n{x_tags}"
    if len(x_text) > 260:
        x_text = x_text[:257].rsplit(" ", 1)[0] + "..."
    facebook = "\n\n".join(
        [
            f"{profile['emoji']} {profile['name']} - {day} spotlight",
            hook,
            cta,
            "Follow the story updates across the main channels.",
            platform_links_block(abbr),
            tags,
        ]
    )
    return {
        "instagram": with_instagram_links(instagram, abbr),
        "x": x_text,
        "facebook": facebook,
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
