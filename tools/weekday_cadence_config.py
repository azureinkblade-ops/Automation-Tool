"""Defaults for the weekday social cadence (phase 1).

These values are the agreed defaults until David changes them. Phase 1 never
publishes (publish_generated_media stays False). Chapter pick defaults to the
newest chapter verified live on Patreon from local release-status records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Tuple

NOVELS: Tuple[str, ...] = ("EN", "HP", "HA", "SF")
STATIC_PLATFORMS: Tuple[str, ...] = ("facebook", "instagram", "x")
VIDEO_PLATFORMS: Tuple[str, ...] = ("tiktok",)

CHAPTER_SOURCE_PATREON = "patreon"
CHAPTER_SOURCE_ROYAL_ROAD = "royal_road"
CHAPTER_SOURCES = frozenset({CHAPTER_SOURCE_PATREON, CHAPTER_SOURCE_ROYAL_ROAD})
DEFAULT_CHAPTER_SOURCE = CHAPTER_SOURCE_PATREON

CHAPTER_PICK_NEWEST_LIVE = "newest_live"
DEFAULT_CHAPTER_PICK = CHAPTER_PICK_NEWEST_LIVE

TIMEZONE_NAME = "America/Phoenix"
IDENTITY_APPROVAL_HOUR = 18  # 6:00 PM the evening before the target weekday

DEFAULT_SHARE_STILL_ACROSS_STATIC = True
X_STATUS = "awaiting_david_post"
TIKTOK_READY_REQUIRES_WAN_SOCIAL_READY = True
PUBLISH_GENERATED_MEDIA = False

OUTPUT_DIRNAME = "daily-social"
OVERRIDE_RELATIVE = "daily-social/patreon_live_overrides.json"
COPY_BANK_RELATIVE = "daily-social/copy-bank/weekday-bank-v1.md"
HASHTAG_SOURCE_PROMO_COPY = "promo_copy.social_profile"
MANIFEST_JSON = "manifest.json"
MANIFEST_MD = "manifest.md"
MANIFEST_CSV = "manifest.csv"
MEDIA_SUBDIR = "media"

SCHEMA_VERSION = 1

STATUS_READY = "ready"
STATUS_HELD = "held"
STATUS_AWAITING_APPROVAL = "awaiting_approval"
STATUS_AWAITING_DAVID = "awaiting_david_post"
STATUSES = frozenset(
    {STATUS_READY, STATUS_HELD, STATUS_AWAITING_APPROVAL, STATUS_AWAITING_DAVID}
)

HOLD_UNVERIFIED_SOURCE = "CHAPTER_SOURCE_UNVERIFIED"
HOLD_IDENTITY_UNAPPROVED = "IDENTITY_UNAPPROVED"
HOLD_MEDIA = "MEDIA_HOLD"
HOLD_SVD = "SVD_FALLBACK_SOCIAL_HOLD"
HOLD_SLIDESHOW = "MEDIA_HOLD:slideshow_not_postable"
HOLD_FRAME_PROBE = "MEDIA_HOLD:FRAME_PROBE_FAILED"
HOLD_DRY_RUN_CLIP = "DRY_RUN:CLIP_STUBBED"
HOLD_NO_STILL = "VIDEO_REQUIRED_MISSING:SOURCE_STILL_MISSING"
HOLD_MEDIA_REQUIRED = "MEDIA_REQUIRED_MISSING"
TIER_INNER = "Inner Disciple"
TIER_PATH = "Path Initiate"
KNOWN_PATREON_TIERS = (TIER_INNER, TIER_PATH)
MEDIA_REQUIRED_PLATFORMS = ("facebook", "instagram")
COMFYUI_PORT = 8188
IDENTITY_CHARACTERS = {
    "EN": "Kael Veyra",
    "HA": "Kai",
    "HP": "Liang",
    "SF": "Jarek",
}

WAN_BACKEND = "wan_22"
SOCIAL_READY = "SOCIAL_READY"
EXPECTED_FRAMES = 73
EXPECTED_FPS = 24
EXPECTED_WIDTH = 1080
EXPECTED_HEIGHT = 1920
MIN_SECONDS = 3.0

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


@dataclass(frozen=True)
class WeekdayCadenceConfig:
    novels: Tuple[str, ...] = NOVELS
    chapter_source: str = DEFAULT_CHAPTER_SOURCE
    chapter_pick: str = DEFAULT_CHAPTER_PICK
    timezone: str = TIMEZONE_NAME
    identity_approval_hour: int = IDENTITY_APPROVAL_HOUR
    share_still_across_static: bool = DEFAULT_SHARE_STILL_ACROSS_STATIC
    x_status: str = X_STATUS
    tiktok_ready_requires_wan_social_ready: bool = TIKTOK_READY_REQUIRES_WAN_SOCIAL_READY
    publish_generated_media: bool = PUBLISH_GENERATED_MEDIA
    output_dirname: str = OUTPUT_DIRNAME

    def __post_init__(self) -> None:
        source = str(self.chapter_source or "").strip().lower()
        if source not in CHAPTER_SOURCES:
            raise ValueError(
                f"chapter_source must be one of {sorted(CHAPTER_SOURCES)}, got {self.chapter_source!r}"
            )
        object.__setattr__(self, "chapter_source", source)
        if bool(self.publish_generated_media):
            raise ValueError("publish_generated_media must stay False for phase 1 cadence builds")
        if int(self.identity_approval_hour) < 0 or int(self.identity_approval_hour) > 23:
            raise ValueError("identity_approval_hour must be 0-23")
        pick = str(self.chapter_pick or "").strip() or DEFAULT_CHAPTER_PICK
        if pick != CHAPTER_PICK_NEWEST_LIVE:
            raise ValueError(f"unsupported chapter_pick: {self.chapter_pick!r}")
        object.__setattr__(self, "chapter_pick", pick)
        status = str(self.x_status or "").strip() or X_STATUS
        if status not in STATUSES:
            raise ValueError(f"x_status must be a known item status, got {self.x_status!r}")
        object.__setattr__(self, "x_status", status)
        novels = tuple(str(n).strip().upper() for n in (self.novels or ()) if str(n).strip())
        if not novels:
            raise ValueError("novels must not be empty")
        object.__setattr__(self, "novels", novels)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None = None) -> "WeekdayCadenceConfig":
        data = dict(raw or {})
        novels = data.get("novels")
        if isinstance(novels, Iterable) and not isinstance(novels, (str, bytes)):
            data["novels"] = tuple(novels)
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return {
            "novels": list(self.novels),
            "chapter_source": self.chapter_source,
            "chapter_pick": self.chapter_pick,
            "timezone": self.timezone,
            "identity_approval_hour": self.identity_approval_hour,
            "share_still_across_static": self.share_still_across_static,
            "x_status": self.x_status,
            "tiktok_ready_requires_wan_social_ready": self.tiktok_ready_requires_wan_social_ready,
            "publish_generated_media": self.publish_generated_media,
            "output_dirname": self.output_dirname,
        }
