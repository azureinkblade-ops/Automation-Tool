"""Produce weekday-cadence stills through the existing chapter-release image pipeline.

Native generation uses app.generate_promo_image_v2 with the Main Posts profile,
the same seam chapter releases use. It does not add a model. Structured
depiction is passed as ImageIntentRequest context, never as prompt wording.
A blocked governed generation never falls back to an old, stock, or banked image.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.weekday_cadence_config import (
    DEPICTION_GOVERNED,
    DEPICTION_NOT_GOVERNED,
    DEPICTION_UNKNOWN,
)

# Main Posts / chapter-release default (tools/main_posts_pipeline_v2.py).
STILL_SIZE_FB_IG = (1024, 1024)
# TikTok / Wan social presentation size (i2v_presentation_adapter DEFAULT_SOCIAL).
STILL_SIZE_TIKTOK = (1080, 1920)
STILL_STYLE = "main-posts"

NOVEL_TITLES = {
    "EN": "Eternal Nexus",
    "HA": "Heavenly Ascension System",
    "SF": "Soul Forge Era",
    "HP": "The Hundredfold Path",
}

GeneratePromo = Callable[..., Any]
ChapterLoader = Callable[[str, int], Mapping[str, Any] | None]


class StillGenerationBlocked(RuntimeError):
    """Raised when the production pipeline refuses a still. Never fall back."""


def novel_title(abbr: str) -> str:
    return NOVEL_TITLES.get(str(abbr).strip().upper(), str(abbr).strip())


def build_still_prompt(
    *,
    novel: str,
    chapter: int | None,
    visual: str = "",
    title: str = "",
) -> str:
    """Prompt from the bank visual line plus chapter context only.

    Does not mention approval, governed characters, or depiction labels.
    """
    parts: list[str] = []
    visual = " ".join(str(visual or "").split())
    if visual:
        parts.append(visual)
    name = novel_title(novel)
    if chapter is not None:
        ctx = f"{name} chapter {int(chapter)}"
    else:
        ctx = name
    if title:
        ctx = f"{ctx}: {str(title).strip()}"
    if ctx:
        parts.append(ctx)
    parts.append("No text or typography.")
    return " ".join(parts).strip()


def structured_image_intent(
    *,
    depiction: str,
    novel: str = "",
    visual: str = "",
    caption: str = "",
) -> Any | None:
    """Structured depiction evidence for the stills pipeline. Never prompt text."""
    try:
        from tools.identity_preservation import (
            ImageIntentRequest,
            governed_character_keys_for_novel,
            governed_characters_in_text,
        )
    except Exception:
        ImageIntentRequest = None  # type: ignore
    evidence = str(depiction or DEPICTION_UNKNOWN).strip() or DEPICTION_UNKNOWN
    if ImageIntentRequest is None:
        if evidence == DEPICTION_GOVERNED:
            return {
                "depicted_characters": [],
                "origin": "weekday_cadence_bank",
            }
        if evidence == DEPICTION_NOT_GOVERNED:
            return {
                "depicted_characters": [],
                "background_only": True,
                "requested_asset_type": "ENVIRONMENT_ONLY",
                "origin": "weekday_cadence_bank",
            }
        return None
    if evidence == DEPICTION_GOVERNED:
        keys = tuple(governed_characters_in_text(f"{visual} {caption}"))
        if not keys:
            try:
                from tools.novel_id import normalize_novel_id
                nid = normalize_novel_id(novel)
            except Exception:
                nid = str(novel or "").strip().casefold()
            keys = tuple(governed_character_keys_for_novel(nid) or ())
        return ImageIntentRequest(
            depicted_characters=keys,
            origin="weekday_cadence_bank",
        )
    if evidence == DEPICTION_NOT_GOVERNED:
        return ImageIntentRequest(
            depicted_characters=(),
            background_only=True,
            requested_asset_type="ENVIRONMENT_ONLY",
            origin="weekday_cadence_bank",
        )
    return None


def load_chapter_context(
    novel: str,
    chapter: int | None,
    *,
    loader: ChapterLoader | None = None,
) -> dict[str, str]:
    if chapter is None:
        return {"title": "", "text": ""}
    load = loader
    if load is None:
        def load(abbr: str, number: int) -> Mapping[str, Any] | None:
            try:
                from app import docs_chapter_text
                return docs_chapter_text(abbr, int(number))
            except Exception:
                return None
    try:
        data = load(str(novel).strip().upper(), int(chapter)) or {}
    except Exception:
        data = {}
    if not isinstance(data, Mapping):
        return {"title": "", "text": ""}
    title = str(data.get("title") or data.get("heading") or "").strip()
    text = str(data.get("text") or data.get("raw_text") or "").strip()
    return {"title": title, "text": text[:800]}


def letterbox_to_size(
    source: Path,
    destination: Path,
    size: tuple[int, int] = STILL_SIZE_TIKTOK,
    *,
    fill: tuple[int, int, int] = (0, 0, 0),
) -> Path:
    """Fit the source inside size (existing I2V FIT_INSIDE + letterbox convention)."""
    from PIL import Image

    src = Path(source)
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as image:
        frame = image.convert("RGB")
        target_w, target_h = int(size[0]), int(size[1])
        scale = min(target_w / frame.width, target_h / frame.height)
        new_w = max(1, int(frame.width * scale))
        new_h = max(1, int(frame.height * scale))
        resized = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), fill)
    canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    canvas.save(dest)
    return dest


def generate_cadence_still(
    novel: str,
    chapter: int | None,
    *,
    target: Path,
    visual: str = "",
    depiction: str = DEPICTION_UNKNOWN,
    caption: str = "",
    chapter_loader: ChapterLoader | None = None,
    generate_promo: GeneratePromo | None = None,
    style: str = STILL_STYLE,
) -> Path:
    """Generate one still with generate_promo_image_v2. No stock/old/banked fallback."""
    if depiction == DEPICTION_UNKNOWN:
        raise StillGenerationBlocked("NO_STRUCTURED_DEPICTION_EVIDENCE")
    context = load_chapter_context(novel, chapter, loader=chapter_loader)
    prompt = build_still_prompt(
        novel=novel,
        chapter=chapter,
        visual=visual,
        title=context.get("title") or "",
    )
    lowered = prompt.lower()
    for banned in ("[approval:", "no governed characters", "needs david's approval"):
        if banned in lowered:
            prompt = prompt.replace("[APPROVAL:", "").replace("[no governed characters]", "")
            # Strip label tokens if a bank visual accidentally included the tag; the
            # visual line itself should already be clean.
    intent = structured_image_intent(
        depiction=depiction,
        novel=novel,
        visual=visual,
        caption=caption,
    )
    scene_text = visual or context.get("text") or ""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    generate = generate_promo
    if generate is None:
        try:
            from app import generate_promo_image_v2 as generate
        except Exception as exc:
            raise StillGenerationBlocked(f"STILL_PIPELINE_UNAVAILABLE:{type(exc).__name__}") from exc
    try:
        source = generate(
            style,
            prompt,
            target,
            abbr=str(novel).strip().upper(),
            index=int(chapter or 0),
            novel=novel_title(novel),
            chapter=chapter,
            scene_text=scene_text or None,
            image_intent=intent,
        )
    except Exception as exc:
        raise StillGenerationBlocked(f"STILL_GENERATION_BLOCKED:{type(exc).__name__}:{exc}") from exc
    if not source:
        raise StillGenerationBlocked("STILL_GENERATION_EMPTY:generate_promo_image_v2 returned no source")
    if not target.is_file():
        raise StillGenerationBlocked("STILL_GENERATION_MISSING_ARTIFACT")
    return target


@dataclass
class CadenceClipAdapter:
    """Map produce_chapter_clip (603cbeb Wan chain) onto ClipResult."""

    store_root: Path
    produce: Callable[..., Any] | None = None

    def __call__(self, still: Path, *, novel: str = "", chapter: int | None = None, **_kwargs: Any):
        from tools.weekday_cadence_posts import ClipResult

        produce = self.produce
        if produce is None:
            from tools.chapter_video_wiring import produce_chapter_clip as produce
        result = produce(
            still,
            workflow_id=f"cadence-{novel}-{chapter}",
            store_root=self.store_root,
            still_approved=True,
            source_character_intent="INTENT_NO",
        )
        path = getattr(result, "asset_path", None)
        return ClipResult(
            outcome=str(getattr(result, "outcome", "") or "MEDIA_HOLD"),
            backend=getattr(result, "backend_used", None),
            social_hold=bool(getattr(result, "social_hold", False)),
            hold_reason=getattr(result, "hold_reason", None),
            frame_count=int(getattr(result, "frame_count", 0) or 0),
            duration_seconds=float(getattr(result, "duration_seconds", 0) or 0),
            width=int(getattr(result, "width", 0) or 0),
            height=int(getattr(result, "height", 0) or 0),
            path=Path(path) if path else None,
            fallback_used=bool(getattr(result, "fallback_used", False)),
            probe_ok=True if str(getattr(result, "outcome", "")) == "SOCIAL_READY" else None,
        )
