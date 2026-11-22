"""Static-post and short-TikTok wrappers for the weekday cadence.

Phase 1 never publishes. make_social_post is optional and is always called with
publish_generated_media=False. The TikTok clip step is injected so dry-run and
tests can stub it; a SOCIAL_READY Wan clip that passes the frame probe is the
only path that marks TikTok ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from tools.weekday_cadence_config import (
    EXPECTED_FRAMES,
    EXPECTED_HEIGHT,
    EXPECTED_WIDTH,
    HOLD_DRY_RUN_CLIP,
    HOLD_FRAME_PROBE,
    HOLD_MEDIA,
    HOLD_MEDIA_REQUIRED,
    HOLD_NO_STILL,
    HOLD_SLIDESHOW,
    HOLD_SVD,
    MEDIA_REQUIRED_PLATFORMS,
    MIN_SECONDS,
    PUBLISH_GENERATED_MEDIA,
    SOCIAL_READY,
    STATUS_HELD,
    STATUS_READY,
    WAN_BACKEND,
    WeekdayCadenceConfig,
)
from tools.weekday_cadence_manifest import CadenceItem

MakeSocialPost = Callable[..., dict[str, Any]]
ProduceClip = Callable[..., "ClipResult"]
FrameProbe = Callable[["ClipResult"], tuple[bool, str]]


class PublishBlocked(RuntimeError):
    """Raised if a cadence build would call a publish path."""


@dataclass
class ClipResult:
    outcome: str
    backend: str | None = None
    social_hold: bool = False
    hold_reason: str | None = None
    frame_count: int = 0
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0
    path: Path | None = None
    fallback_used: bool = False
    kind: str = ""
    probe_ok: bool | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return (
            self.outcome == SOCIAL_READY
            and not self.social_hold
            and str(self.backend or "") == WAN_BACKEND
        )


def force_no_publish(**kwargs: Any) -> dict[str, Any]:
    """Return kwargs safe for make_social_post. Never allows publish=True."""
    if kwargs.get("publish_generated_media") is True:
        raise PublishBlocked("weekday cadence forbids publish_generated_media=True")
    kwargs["publish_generated_media"] = PUBLISH_GENERATED_MEDIA
    return kwargs


def call_make_social_post(
    make_social_post: MakeSocialPost,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    return make_social_post(*args, **force_no_publish(**kwargs))


def default_captions(novel: str, chapter: int | None, source_platform: str) -> dict[str, str]:
    chapter_text = "an already-released chapter" if chapter is None else f"Ch. {chapter}"
    source = "Patreon" if source_platform == "patreon" else "Royal Road"
    hook = f"{novel} {chapter_text} is live on {source}."
    cta = "Start reading: link in bio."
    return {
        "facebook": f"{hook}\n\n{cta}",
        "instagram": f"{hook}\n\n{cta}",
        "x": f"{hook}\n{cta}",
        "tiktok": f"{hook} {cta}",
    }


def apply_shared_still(items: Sequence[CadenceItem], relative_name: str) -> None:
    for item in items:
        if item.platform in {"facebook", "instagram", "x"}:
            item.media = [relative_name]




def apply_media_required_holds(items: Sequence[CadenceItem]) -> list[CadenceItem]:
    """Instagram always needs media; Facebook does in this weekday plan.

    An item on those platforms with no media must never stay `ready`.
    Other statuses (held, awaiting_approval, awaiting_david_post) are left alone.
    """
    for item in items:
        if item.platform not in MEDIA_REQUIRED_PLATFORMS:
            continue
        if item.media:
            continue
        if item.status == STATUS_READY:
            item.status = STATUS_HELD
            item.hold_reason = HOLD_MEDIA_REQUIRED
    return list(items)


def default_frame_probe(clip: ClipResult) -> tuple[bool, str]:
    if clip.probe_ok is False:
        return False, clip.hold_reason or HOLD_FRAME_PROBE
    if clip.probe_ok is True:
        frames_ok = int(clip.frame_count) == EXPECTED_FRAMES
        size_ok = int(clip.width) == EXPECTED_WIDTH and int(clip.height) == EXPECTED_HEIGHT
        duration_ok = float(clip.duration_seconds) + 1e-6 >= MIN_SECONDS
        if frames_ok and size_ok and duration_ok:
            return True, ""
        return False, HOLD_FRAME_PROBE
    frames_ok = int(clip.frame_count) == EXPECTED_FRAMES
    size_ok = int(clip.width) == EXPECTED_WIDTH and int(clip.height) == EXPECTED_HEIGHT
    duration_ok = float(clip.duration_seconds) + 1e-6 >= MIN_SECONDS
    if frames_ok and size_ok and duration_ok:
        return True, ""
    return False, HOLD_FRAME_PROBE


def evaluate_tiktok_clip(
    clip: ClipResult | None,
    *,
    config: WeekdayCadenceConfig,
    probe: FrameProbe | None = None,
) -> tuple[str, str | None]:
    if clip is None:
        return STATUS_HELD, HOLD_NO_STILL
    kind = str(clip.kind or "").lower()
    if kind in {"slideshow", "legacy_slideshow"}:
        return STATUS_HELD, HOLD_SLIDESHOW
    if clip.social_hold or clip.backend == "svd_xt_1_1" or clip.hold_reason == HOLD_SVD:
        return STATUS_HELD, clip.hold_reason or HOLD_SVD
    if clip.outcome != SOCIAL_READY:
        return STATUS_HELD, clip.hold_reason or HOLD_MEDIA
    if config.tiktok_ready_requires_wan_social_ready and str(clip.backend or "") != WAN_BACKEND:
        return STATUS_HELD, clip.hold_reason or HOLD_MEDIA
    checker = probe or default_frame_probe
    ok, why = checker(clip)
    if not ok:
        return STATUS_HELD, why or HOLD_FRAME_PROBE
    return STATUS_READY, None


def build_tiktok_item(
    item: CadenceItem,
    *,
    still: Path | None,
    approved: bool,
    config: WeekdayCadenceConfig,
    produce_clip: ProduceClip | None,
    dry_run: bool = False,
    probe: FrameProbe | None = None,
) -> tuple[CadenceItem, ClipResult | None]:
    if item.status == STATUS_HELD and item.hold_reason:
        return item, None
    if item.status == "awaiting_approval":
        return item, None
    if still is None:
        item.status = STATUS_HELD
        item.hold_reason = HOLD_NO_STILL
        return item, None
    if not approved:
        return item, None
    if dry_run or produce_clip is None:
        item.status = STATUS_HELD
        item.hold_reason = HOLD_DRY_RUN_CLIP
        return item, None
    clip = produce_clip(still)
    status, reason = evaluate_tiktok_clip(clip, config=config, probe=probe)
    item.status = status
    item.hold_reason = reason
    return item, clip


def stub_produce_clip(*_args: Any, **_kwargs: Any) -> ClipResult:
    """Default clip producer: never starts ComfyUI or ffmpeg."""
    return ClipResult(outcome="MEDIA_HOLD", hold_reason=HOLD_DRY_RUN_CLIP, kind="stub")
