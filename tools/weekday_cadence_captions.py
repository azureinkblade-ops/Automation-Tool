"""Optional Writer copy-bank captions and per-novel hashtag attachment.

The two-week bank is an optional source. An item is used only when its source
chapter is the chapter the picker allowed for that novel. Otherwise the build
falls back to generated copy. Facebook and Instagram captions then receive the
novel hashtag set from promo_copy.social_profile (repo config). Tags already
present in the caption are not repeated. X captions are left unchanged.
"""

from __future__ import annotations

from tools.weekday_cadence_config import KNOWN_PATREON_TIERS, TIER_INNER, TIER_PATH

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tools.weekday_cadence_config import STATIC_PLATFORMS

DEFAULT_BANK_RELATIVE = "daily-social/copy-bank/weekday-bank-v1.md"
HASHTAG_SOURCE_PROMO_COPY = "promo_copy.social_profile"
HASHTAG_SOURCE_WRITER_BANK = "daily-social/copy-bank/weekday-bank-v1.md"

# Facebook suppresses hashtag-heavy posts; promo_copy._limit_hashtags uses 5.
FACEBOOK_HASHTAG_LIMIT = 5
INSTAGRAM_HASHTAG_LIMIT = 9

BANK_HASHTAGS = {
    "EN": ["#EternalNexus", "#cultivation", "#webnovel", "#progressionfantasy", "#xianxia", "#serialfiction"],
    "HP": ["#TheHundredfoldPath", "#cultivation", "#webnovel", "#progressionfantasy", "#xianxia", "#serialfiction"],
    "HA": ["#HeavenlyAscensionSystem", "#cultivation", "#webnovel", "#litrpg", "#progressionfantasy", "#serialfiction"],
    "SF": ["#SoulforgeEra", "#cultivation", "#webnovel", "#darkfantasy", "#progressionfantasy", "#serialfiction"],
}

_ITEM_HEADER = re.compile(
    r"^\*\*(TikTok|FB/IG post|X post)\*\*\s*\[source\s+([A-Z]{2})-(\d+)\]",
    re.MULTILINE,
)
_DAY_HEADER = re.compile(
    r"^## Day\s+(\d+)\s+\(Week\s+\d+,\s+(Monday|Tuesday|Wednesday|Thursday|Friday)\)\s*$",
    re.MULTILINE,
)
_SUPPLEMENT_HEADER = re.compile(r"^## Supplement\b", re.MULTILINE)
_CAPTION_LINE = re.compile(r"^- Caption:\s*(.*)$", re.MULTILINE)
_TEXT_LINE = re.compile(r"^- Text:\s*(.*)$", re.MULTILINE)
_HASHTAG_LINE = re.compile(r"^(#\w+(?:\s+#\w+)*)\s*$")

KIND_TO_PLATFORMS = {
    "TikTok": ("tiktok",),
    "FB/IG post": ("facebook", "instagram"),
    "X post": ("x",),
}


@dataclass(frozen=True)
class BankCaption:
    novel: str
    chapter: int
    kind: str
    platforms: tuple[str, ...]
    text: str
    weekday: str | None
    needs_approval: bool
    source: str = "copy_bank"
    bank_day: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "novel": self.novel,
            "chapter": self.chapter,
            "kind": self.kind,
            "platforms": list(self.platforms),
            "text": self.text,
            "weekday": self.weekday,
            "needs_approval": self.needs_approval,
            "source": self.source,
            "bank_day": self.bank_day,
        }


def _section_map(text: str) -> list[tuple[int, int | None, str | None]]:
    """(position, bank_day or None, weekday or None). Supplement marks have no day."""
    marks: list[tuple[int, int | None, str | None]] = []
    for match in _DAY_HEADER.finditer(text):
        marks.append((match.start(), int(match.group(1)), match.group(2)))
    for match in _SUPPLEMENT_HEADER.finditer(text):
        marks.append((match.start(), None, None))
    marks.sort(key=lambda item: item[0])
    return marks


def _section_at(pos: int, marks: Sequence[tuple[int, int | None, str | None]]) -> tuple[int | None, str | None]:
    current: tuple[int | None, str | None] = (None, None)
    for start, day, weekday in marks:
        if start <= pos:
            current = (day, weekday)
        else:
            break
    return current


def _block_text(text: str, start: int, end: int) -> str:
    return text[start:end].strip()


def _extract_tiktok_caption(block: str) -> str:
    match = _CAPTION_LINE.search(block)
    if not match:
        return ""
    caption = match.group(1).strip()
    rest = block[match.end():].lstrip("\n")
    first_line = rest.splitlines()[0].strip() if rest.splitlines() else ""
    if _HASHTAG_LINE.match(first_line):
        caption = f"{caption}\n{first_line}"
    return caption.strip()


def _extract_fb_ig_text(block: str) -> str:
    match = _TEXT_LINE.search(block)
    if not match:
        return ""
    line = match.group(1).strip()
    # Continuation lines after "- Text:" until a blank line or next heading
    after = block[match.end():]
    extra: list[str] = []
    for raw in after.splitlines():
        if not raw.strip():
            break
        if raw.startswith("- ") or raw.startswith("#") or raw.startswith("**") or raw.startswith("###"):
            break
        extra.append(raw.strip())
    if extra:
        return (line + " " + " ".join(extra)).strip()
    return line


def _extract_x_text(block: str) -> str:
    lines = block.splitlines()
    body: list[str] = []
    started = False
    for raw in lines[1:]:
        if raw.startswith("###") or raw.startswith("## ") or raw.startswith("**"):
            break
        if not started and not raw.strip():
            continue
        started = True
        if not raw.strip():
            break
        if raw.startswith("- "):
            continue
        body.append(raw.strip())
    return " ".join(body).strip()


def parse_copy_bank(text: str) -> list[BankCaption]:
    marks = _section_map(text)
    matches = list(_ITEM_HEADER.finditer(text))
    items: list[BankCaption] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        # Don't swallow a reel/day heading's following items; the next match already bounds us.
        block = _block_text(text, match.start(), end)
        kind, abbr, chapter_s = match.group(1), match.group(2), match.group(3)
        platforms = KIND_TO_PLATFORMS.get(kind)
        if not platforms:
            continue
        if kind == "TikTok":
            body = _extract_tiktok_caption(block)
        elif kind == "FB/IG post":
            body = _extract_fb_ig_text(block)
        else:
            body = _extract_x_text(block)
        if not body:
            continue
        bank_day, weekday = _section_at(match.start(), marks)
        items.append(
            BankCaption(
                novel=abbr,
                chapter=int(chapter_s),
                kind=kind,
                platforms=platforms,
                text=body,
                weekday=weekday,
                needs_approval="[APPROVAL:" in block,
                bank_day=bank_day,
            )
        )
    return items


def load_copy_bank(path: Path | None) -> list[BankCaption]:
    if path is None:
        return []
    file_path = Path(path)
    if not file_path.is_file():
        return []
    try:
        return parse_copy_bank(file_path.read_text(encoding="utf-8"))
    except OSError:
        return []


def select_bank_caption(
    items: Sequence[BankCaption],
    *,
    novel: str,
    chapter: int | None,
    platform: str,
    weekday: str | None = None,
    allowed_chapters: Iterable[int] | None = None,
    bank_day: int | None = None,
) -> BankCaption | None:
    if chapter is None:
        return None
    abbr = str(novel).strip().upper()
    plat = str(platform).strip().lower()
    allowed = set(int(n) for n in allowed_chapters) if allowed_chapters is not None else {int(chapter)}
    if int(chapter) not in allowed:
        return None
    matches = [
        item
        for item in items
        if item.novel == abbr and item.chapter == int(chapter) and plat in item.platforms
    ]
    if not matches:
        return None
    if bank_day is not None:
        day_hits = [item for item in matches if item.bank_day == int(bank_day)]
        if day_hits:
            matches = day_hits
    if weekday:
        named = [item for item in matches if item.weekday == weekday]
        if named:
            return named[0]
    return matches[0]


def extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#\w+", text or "")


def hashtags_from_promo_copy(novel: str) -> list[str]:
    from promo_copy import social_profile

    profile = social_profile(novel)
    return extract_hashtags(str(profile.get("hashtags") or ""))


def novel_hashtag_set(novel: str) -> tuple[list[str], str]:
    """Return (tags, source). Prefers repo promo_copy.social_profile."""
    try:
        tags = hashtags_from_promo_copy(novel)
    except Exception:
        tags = []
    if tags:
        return tags, HASHTAG_SOURCE_PROMO_COPY
    fallback = list(BANK_HASHTAGS.get(str(novel).strip().upper()) or [])
    return fallback, HASHTAG_SOURCE_WRITER_BANK


def append_hashtags(caption: str, tags: Sequence[str], *, limit: int | None = None) -> str:
    text = str(caption or "").rstrip()
    existing = {tag.lower() for tag in extract_hashtags(text)}
    add: list[str] = []
    already = len(existing)
    for tag in tags:
        token = str(tag).strip()
        if not token:
            continue
        if not token.startswith("#"):
            token = "#" + token
        if token.lower() in existing:
            continue
        if limit is not None and already + len(add) >= limit:
            break
        add.append(token)
        existing.add(token.lower())
    if not add:
        return text
    return f"{text}\n\n{' '.join(add)}" if text else " ".join(add)


def apply_platform_hashtags(
    caption: str,
    *,
    novel: str,
    platform: str,
) -> tuple[str, str | None]:
    plat = str(platform).strip().lower()
    if plat == "x":
        return str(caption or "").rstrip(), None
    if plat not in {"facebook", "instagram"}:
        # TikTok bank captions already carry tags; don't force a second set.
        return str(caption or "").rstrip(), None
    tags, source = novel_hashtag_set(novel)
    limit = FACEBOOK_HASHTAG_LIMIT if plat == "facebook" else INSTAGRAM_HASHTAG_LIMIT
    return append_hashtags(caption, tags, limit=limit), source




_TIER_NAME_RE = re.compile(r"(?i)\b(inner\s+disciple|path\s+initiate)\b")
_TIER_JOIN_RE = re.compile(r"(?i)\s*(?:and|&|/|or)\s*$")


def live_tiers_are_complete(live_tiers: Iterable[str] | None) -> bool:
    present = {str(item).strip() for item in (live_tiers or []) if str(item).strip()}
    return all(tier in present for tier in KNOWN_PATREON_TIERS)


def caption_mentions_tier(text: str) -> bool:
    return bool(_TIER_NAME_RE.search(str(text or "")))


def sanitize_caption_for_tiers(caption: str, live_tiers: Iterable[str] | None) -> str:
    """If a chapter is not live on every paid tier, do not name a tier.

    Captions may still say the chapter is live now on Patreon. Partial chapters
    such as EN-140 (Inner Disciple only) must not name Inner Disciple or Path
    Initiate, so a reader is not promised a post on a tier that is not live.
    """
    text = str(caption or "")
    if live_tiers_are_complete(live_tiers):
        return text
    stripped = _TIER_NAME_RE.sub("", text)
    # Collapse leftover "for  members" / double spaces after removals.
    stripped = re.sub(r"[ \t]{2,}", " ", stripped)
    stripped = re.sub(r" ?\n ?\n ?", "\n\n", stripped)
    return stripped.strip()


def captions_for_novel(
    *,
    novel: str,
    chapter: int | None,
    source_platform: str,
    weekday: str | None,
    bank: Sequence[BankCaption],
    allowed_chapters: Iterable[int] | None,
    fallback: Mapping[str, str],
    live_tiers: Iterable[str] | None = None,
) -> dict[str, str]:
    from tools.weekday_cadence_posts import default_captions

    base = dict(fallback or default_captions(novel, chapter, source_platform))
    allowed = list(allowed_chapters) if allowed_chapters is not None else (
        [int(chapter)] if chapter is not None else []
    )
    for platform in (*STATIC_PLATFORMS, "tiktok"):
        picked = select_bank_caption(
            bank,
            novel=novel,
            chapter=chapter,
            platform=platform,
            weekday=weekday,
            allowed_chapters=allowed,
        )
        if picked is not None:
            base[platform] = picked.text
        text, _source = apply_platform_hashtags(base.get(platform, ""), novel=novel, platform=platform)
        base[platform] = sanitize_caption_for_tiers(text, live_tiers)
    return base
