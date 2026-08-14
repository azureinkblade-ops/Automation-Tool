"""Media-pack builders for the Automation Tool (Task 2 of the monolith extraction).

Holds the campaign / social-image / TikTok / Shorts pack *construction* logic that
performs real side-effects (file writes, asset copying, ffmpeg, image-gen, DB/ledger
writes, auto-publish). This module imports ONLY ``promo_copy`` (pure copy), ``app_config``
(constants), ``app_state`` (runtime caches), and ``automation_db`` (DB access). It MUST
NOT import ``app``.

The side-effecting helpers and pure app-level helpers that are NOT yet extracted into
their own modules (Tasks 3-6 own them) are supplied through a ``collaborators`` dict
(default = safe stubs so the module imports and runs standalone). At Task 8 (inversion)
``app.py`` will pass the real app functions, e.g.::

    from promo_builder import make_social_post
    make_social_post(..., collaborators={name: getattr(app, name) for name in REQUIRED_COLLABORATORS})

Behavior is preserved verbatim from app.py. See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 2).
"""

from __future__ import annotations

import json
import random
import shutil
import time
from pathlib import Path
from typing import Any, Callable

import app_config as config
import promo_copy as copy
import promo_copy as promo_copy_module

# Re-exported config constants / helpers used below.
NOVEL_NAMES = config.NOVEL_NAMES
LORA_STYLE_TRACKS = config.LORA_STYLE_TRACKS
TIKTOK_OUTPUT_DIR = config.TIKTOK_OUTPUT_DIR
DAYS = config.DAYS
SOCIAL_PROMPT_FILE = config.SOCIAL_PROMPT_FILE
PATREON_URL = config.PATREON_URL
YOUTUBE_SOCIAL_URL = config.YOUTUBE_SOCIAL_URL
TIKTOK_URL = config.TIKTOK_URL

# Pure copy helpers now live in promo_copy.
social_profile = copy.social_profile
rotated_hashtags = copy.rotated_hashtags
rotated_x_hashtags = copy.rotated_x_hashtags
rotating_post_focus = copy.rotating_post_focus
rotating_caption_style = copy.rotating_caption_style
focused_social_cta = copy.focused_social_cta
platform_links_block = copy.platform_links_block
resolve_post_focus = copy.resolve_post_focus
linktree_url = copy.linktree_url
royal_road_url_for_story = copy.royal_road_url_for_story
with_instagram_links = copy.with_instagram_links
fallback_social_copy = copy.fallback_social_copy


# --- collaborator stubs (overridden at Task 8 by app.py) ---
def _stub_raise(name: str):
    def _fn(*args, **kwargs):
        raise NotImplementedError(
            f"promo_builder: collaborator '{name}' not injected. "
            f"app.py must pass collaborators={{'{name}': <real fn>}} at Task 8."
        )
    return _fn


# Required collaborators (functions still owned by app.py / future modules):
REQUIRED_COLLABORATORS = [
    "list_tiktok_assets",        # pure: reads asset manifest (Task 3/state)
    "stable_chapter_folder",     # pure: build output path
    "reusable_pack_result",      # reads prior pack result (state)
    "tiktok_caption",            # pure: caption string
    "instagram_reel_caption",    # pure: caption string
    "youtube_shorts_metadata",   # pure: title/description
    "build_reel_short_copy",     # pure: agent-aware Reel/Short copy (hook/body/caption/title)
    "shortform_seo_keywords",    # pure: deterministic SEO keyword set
    "prepare_tiktok_outro_image",# side-effect: writes outro image
    "tiktok_chapter_teaser_overlays",  # pure: overlay list
    "write_tiktok_video_helper", # side-effect: ffmpeg video
    "generate_deep_tiktok_narration",  # side-effect: local-first TTS voiceover (fail-soft)
    "tiktok_narration_text",  # pure: derives a speakable narration sentence from the caption
    "reset_generated_folder",    # side-effect: clears folder
    "list_daily_promo_images",   # pure: reads promo image manifest
    "social_post_folder",        # pure: build output path
    "generate_tiktok_images",    # side-effect: image-gen (Task 5)
    "create_fresh_social_image_from_caption",  # side-effect: image-gen (Task 5)
    "social_copy_with_openai",   # side-effect: OpenAI network (Task 5)
    "auto_publish_generated_media",  # side-effect: publish (Task 6)
    "update_chapter_ledger",     # side-effect: DB write (Task 3)
]


def _default_collaborators() -> dict[str, Any]:
    return {name: _stub_raise(name) for name in REQUIRED_COLLABORATORS}


# Module-global collaborator registry. app.py populates this once via set_collaborators()
# at startup; the public fns fall back to it when no per-call collaborators are passed.
_COLLAB: dict[str, Any] = _default_collaborators()


def set_collaborators(collab: dict[str, Any]) -> None:
    """Wire the real app.py functions (and data) into this module. Call once at startup."""
    global _COLLAB
    _COLLAB = dict(collab)


def get_collaborators() -> dict[str, Any]:
    return dict(_COLLAB)


def _get(collab: dict[str, Any], name: str):
    fn = collab.get(name)
    if fn is None:
        fn = _stub_raise(name)
    return fn


def _shortform_copy_bundle(
    collab: dict[str, Any],
    abbr: str,
    novel: str,
    chapter: str,
    agent_copy: dict | None,
) -> dict[str, Any]:
    """Assemble the Reel / Shorts copy for one pack.

    When validated agent copy is present (a non-empty caption), the Reel caption and the
    Shorts title/description are sourced from the injected ``build_reel_short_copy``
    collaborator; otherwise the pre-existing generic collaborators are called unchanged so
    the fallback output stays byte-identical.

    This module never calls Hermes: ``agent_copy`` arrives already resolved from app.py.
    """
    agent_consumed = bool(agent_copy) and bool(str((agent_copy or {}).get("caption") or "").strip())
    if not agent_consumed:
        shorts = _get(collab, "youtube_shorts_metadata")(novel, chapter)
        return {
            "agent_used": False,
            "seo_keywords": [],
            "instagram_reel_caption": copy.public_copy_without_links(
                _get(collab, "instagram_reel_caption")(novel, chapter), "instagram"
            ),
            "youtube_shorts_title": shorts["title"],
            "youtube_shorts_description": copy.public_copy_without_links(shorts["description"], "youtube"),
        }
    keywords = _get(collab, "shortform_seo_keywords")(abbr, chapter, agent_copy)
    seo_context = {"abbr": abbr, "keywords": keywords}
    reel = _get(collab, "build_reel_short_copy")(
        agent_copy, novel, chapter, seo_context, platform="instagram_reel"
    )
    short = _get(collab, "build_reel_short_copy")(
        agent_copy, novel, chapter, seo_context, platform="youtube_short"
    )
    return {
        "agent_used": True,
        "seo_keywords": list(keywords or []),
        "instagram_reel_caption": copy.public_copy_without_links(reel["caption"], "instagram"),
        "youtube_shorts_title": short["title"],
        "youtube_shorts_description": copy.public_copy_without_links(short["caption"], "youtube"),
    }


def _stamp_agent_meta(agent_meta: dict[str, Any] | None, agent_used: bool, agent_copy: dict | None) -> None:
    """Record truthful short-form provenance on the shared `agent_meta` dict.

    Single source of truth for the otherwise-triplicated (_shortform_copy_bundle reuse +
    fresh, and the daily-post path) stamping logic. `_agent_used` reflects ACTUAL
    downstream consumption, never merely "agent_copy is not None". `_agent_source` is
    pinned to the Hermes boundary only when copy was consumed.
    """
    if agent_meta is None:
        return
    agent_meta["_agent_used"] = bool(agent_used)
    if agent_used:
        agent_meta.setdefault("_agent_source", (agent_copy or {}).get("_source") or "hermes_agent")


def _apply_agent_provenance(target: dict[str, Any], agent_meta: dict[str, Any] | None) -> None:
    """Project internal `_agent_*` keys onto a pack `metadata.json` payload.

    Strips any pre-existing `_agent_*` keys first so a flag-off rebuild of an earlier
    agent-enabled pack returns to a clean, agent-free metadata state (no stale
    `_agent_run_id` / `_agent_source` left behind to mis-attribute template copy).
    """
    for key in [k for k in target if str(k).startswith("_agent_")]:
        del target[key]
    for key, value in (agent_meta or {}).items():
        if str(key).startswith("_agent_"):
            target[key] = value


def make_tiktok_pack(
    abbr: str,
    chapter: str | None = None,
    force_new_images: bool = False,
    visual_prompt: str = "",
    chapter_text: str = "",
    style: str = "main-posts",
    agent_copy: dict | None = None,
    agent_meta: dict | None = None,
    *,
    collaborators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collab = collaborators if collaborators is not None else _COLLAB
    # Single-style lock (Workstream E): pick ONE track for the whole pack. Default main-posts;
    # caller may request realistic-posts / comic-style. We filter the asset group to that track and
    # regenerate if we don't have >=3 on-style images, so the video never mixes styles.
    pack_track = style if style in LORA_STYLE_TRACKS else "main-posts"
    assets = _get(collab, "list_tiktok_assets")()
    groups = [group for group in assets["imageGroups"] if group["abbr"] == abbr]
    if chapter:
        groups = [group for group in groups if group["chapter"] == str(chapter)]
    if not groups:
        raise RuntimeError(f"No TikTok image group found for {abbr}{' chapter ' + str(chapter) if chapter else ''}.")
    group = groups[-1] if not chapter else groups[0]
    # Filter to on-style assets using the recorded track sidecars (E1).
    files = group.get("files", [])
    tracks = group.get("tracks", [""] * len(files))
    on_style = [f for f, t in zip(files, tracks) if t == pack_track]
    if len(on_style) < 3:
        # Not enough on-style assets: regenerate this chapter's images in pack_track (generate-missing).
        generated = _get(collab, "generate_tiktok_images")(
            abbr, str(group["chapter"]), visual_prompt,
            force_new_images=True, chapter_text=chapter_text, style=pack_track,
        )
        on_style = generated.get("created", [])[:3] or on_style
    group = {**group, "files": on_style[:3]}
    sounds = assets["sounds"]
    if not sounds:
        raise RuntimeError("No TikTok sound files were found.")
    sound = random.choice(sounds)
    folder = _get(collab, "stable_chapter_folder")(TIKTOK_OUTPUT_DIR, "tiktok", f"{abbr} Chapter {group['chapter']}", abbr, group["chapter"])
    reused = _get(collab, "reusable_pack_result")(folder, required_files=["caption.txt", "instagram-reel-caption.txt", "youtube-shorts-description.txt"])
    if not force_new_images and reused and reused.get("chapter") == group["chapter"] and reused.get("abbr") == abbr:
        novel = NOVEL_NAMES.get(abbr, abbr)
        # Reused packs must NOT silently revert to generic copy: prefer the
        # validated agent caption, falling back to the template only when it
        # is unavailable (fail-soft). Same logic as the fresh branch below.
        _template_caption = _get(collab, "tiktok_caption")(novel, group["chapter"])
        _agent_caption = str((agent_copy or {}).get("caption") or "").strip()
        reused["caption"] = copy.public_copy_without_links(_agent_caption or _template_caption, "tiktok")
        # Reused packs must NOT silently revert to generic copy: apply the same
        # agent-aware assembly the fresh branch uses.
        bundle = _shortform_copy_bundle(collab, abbr, novel, group["chapter"], agent_copy)
        reused["instagram_reel_caption"] = bundle["instagram_reel_caption"]
        reused["youtube_shorts_title"] = bundle["youtube_shorts_title"]
        reused["youtube_shorts_description"] = bundle["youtube_shorts_description"]
        reused["seo_keywords"] = bundle["seo_keywords"]
        # Stamp truthful provenance and strip any stale _agent_* left by an earlier
        # agent-enabled build so a flag-off rebuild is clean (no mis-attribution).
        _stamp_agent_meta(agent_meta, bundle["agent_used"], agent_copy)
        _apply_agent_provenance(reused, agent_meta)
        (folder / "caption.txt").write_text(reused["caption"] + "\n", encoding="utf-8")
        (folder / "instagram-reel-caption.txt").write_text(reused["instagram_reel_caption"] + "\n", encoding="utf-8")
        (folder / "youtube-shorts-title.txt").write_text(reused["youtube_shorts_title"] + "\n", encoding="utf-8")
        (folder / "youtube-shorts-description.txt").write_text(reused["youtube_shorts_description"] + "\n", encoding="utf-8")
        image_files = [str(folder / Path(value).name) for value in reused.get("images", []) or [] if (folder / Path(value).name).exists()]
        sound_value = str(reused.get("sound") or "")
        sound_path = folder / Path(sound_value).name if sound_value else None
        overlays = _get(collab, "tiktok_chapter_teaser_overlays")(abbr, group["chapter"], novel, chapter_text=chapter_text, fallback_text=visual_prompt or reused["caption"])
        if len(image_files) < 4:
            image_files = image_files[:3] + [_get(collab, "prepare_tiktok_outro_image")(folder, abbr, novel, group["chapter"], style=pack_track)]
            reused["images"] = image_files
        reused["video_overlays"] = overlays
        reused["pack_track"] = pack_track
        if len(image_files) >= 3 and sound_path and sound_path.exists():
            narration_src = overlays[0].replace("\n", " ").strip() if overlays else ""
            narration_file = _get(collab, "generate_deep_tiktok_narration")(folder, abbr, narration_src) if narration_src else None
            _get(collab, "write_tiktok_video_helper")(folder, image_files[:4], sound_path, overlays=overlays, narration=narration_file)
        (folder / "metadata.json").write_text(json.dumps(reused, indent=2), encoding="utf-8")
        try:
            _get(collab, "update_chapter_ledger")(
                abbr,
                group["chapter"],
                {
                    "shortsReelsBuilt": True,
                    "shortsPackBuilt": True,
                    "shortsPackBuiltAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "shortsFolder": str(folder),
                    "folders": {"shorts": str(folder)},
                },
            )
        except Exception:
            pass
        return reused
    _get(collab, "reset_generated_folder")(folder)
    copied_images: list[str] = []
    for image in group["files"][:3]:
        source = Path(image)
        target = folder / source.name
        shutil.copy2(source, target)
        # Carry the style-track sidecar into the pack folder so the pack is self-describing (E/F).
        sidecar = source.with_name(f"{source.name}.track")
        if sidecar.exists():
            shutil.copy2(sidecar, folder / sidecar.name)
        copied_images.append(str(target))
    sound_source = Path(sound["path"])
    sound_target = folder / sound_source.name
    shutil.copy2(sound_source, sound_target)
    novel = NOVEL_NAMES.get(abbr, abbr)
    # Prefer the validated agent caption; fall back to the deterministic
    # template only when differentiated copy is unavailable (fail-soft).
    _template_caption = _get(collab, "tiktok_caption")(novel, group["chapter"])
    _agent_caption = str((agent_copy or {}).get("caption") or "").strip()
    caption = copy.public_copy_without_links(_agent_caption or _template_caption, "tiktok")
    bundle = _shortform_copy_bundle(collab, abbr, novel, group["chapter"], agent_copy)
    reel_caption = bundle["instagram_reel_caption"]
    shorts_title = bundle["youtube_shorts_title"]
    shorts_description = bundle["youtube_shorts_description"]
    # Stamp truthful provenance (single source of truth) before building the payload.
    _stamp_agent_meta(agent_meta, bundle["agent_used"], agent_copy)
    copied_images.append(_get(collab, "prepare_tiktok_outro_image")(folder, abbr, novel, group["chapter"], style=pack_track))
    overlays = _get(collab, "tiktok_chapter_teaser_overlays")(abbr, group["chapter"], novel, chapter_text=chapter_text, fallback_text=visual_prompt or caption)
    payload = {
        "abbr": abbr,
        "pack_track": pack_track,
        "novel": novel,
        "chapter": group["chapter"],
        "images": copied_images,
        "sound": str(sound_target),
        "caption": caption,
        "instagram_reel_caption": reel_caption,
        "youtube_shorts_title": shorts_title,
        "youtube_shorts_description": shorts_description,
        "folder": str(folder),
        "visual_prompt": visual_prompt,
        "video_overlays": overlays,
    }
    payload["seo_keywords"] = bundle["seo_keywords"]
    # Provenance is internal-only: metadata.json, never public post copy.
    _apply_agent_provenance(payload, agent_meta)
    (folder / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    (folder / "instagram-reel-caption.txt").write_text(reel_caption + "\n", encoding="utf-8")
    (folder / "youtube-shorts-title.txt").write_text(shorts_title + "\n", encoding="utf-8")
    (folder / "youtube-shorts-description.txt").write_text(shorts_description + "\n", encoding="utf-8")
    (folder / "sound.txt").write_text(str(sound_target) + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    narration_src = _get(collab, "tiktok_narration_text")({"caption": caption}, overlays) if caption else (overlays[0].replace("\n", " ").strip() if overlays else "")
    narration_file = _get(collab, "generate_deep_tiktok_narration")(folder, abbr, narration_src) if narration_src else None
    _get(collab, "write_tiktok_video_helper")(folder, copied_images, sound_target, overlays=overlays, narration=narration_file)
    try:
        _get(collab, "update_chapter_ledger")(
            abbr,
            group["chapter"],
            {
                "shortsReelsBuilt": True,
                "shortsPackBuilt": True,
                "shortsPackBuiltAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                "shortsFolder": str(folder),
                "folders": {"shorts": str(folder)},
            },
        )
    except Exception:
        pass
    return payload


def make_social_post(
    abbr: str,
    day: str,
    prompt_template: str,
    use_openai: bool,
    post_focus: str = "",
    chapter_number: str | int = "",
    agent_copy: dict | None = None,
    agent_meta: dict | None = None,
    *,
    collaborators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collab = collaborators if collaborators is not None else _COLLAB
    matches = [
        item
        for item in _get(collab, "list_daily_promo_images")()
        if item["abbr"] == abbr and item["day"].lower() == day.lower()
    ]
    if not matches:
        raise RuntimeError(f"No daily promo image found for {abbr} {day}.")
    item = matches[0]
    folder = _get(collab, "social_post_folder")(abbr, item["day"], chapter_number)
    _get(collab, "reset_generated_folder")(folder)

    agent_consumed = bool(agent_copy) and bool(str((agent_copy or {}).get("caption") or "").strip())
    if agent_consumed:
        # Agent-differentiated copy path (Hermes boundary supplies agent_copy; this
        # module only forwards it to the pure assembly helper and never calls Hermes).
        source = "hermes_agent"
        material = {
            "abbr": abbr,
            "novel": item["novel"],
            "phrases": [],
            "chapter": str(chapter_number) or "",
        }
        platform_posts = promo_copy_module.build_platform_posts(
            item["novel"],
            str(chapter_number) or "",
            material,
            post_focus,
            agent_copy=agent_copy,
        )
        copy = {
            "instagram": platform_posts.get("caption", ""),
            "x": platform_posts.get("x_post", ""),
            "facebook": platform_posts.get("facebook_post", ""),
            "patreon": platform_posts.get("patreon_note", ""),
            "alt_text": f"Promotional image for {item['novel']}, scheduled for {item['day']}.",
            "caption_style": platform_posts.get("caption_style", ""),
            "post_focus": platform_posts.get("post_focus", ""),
        }
    else:
        source = "fallback"
        try:
            if use_openai:
                copy = _get(collab, "social_copy_with_openai")(prompt_template, item["novel"], abbr, item["day"], item["filename"])
                source = "openai"
            else:
                raise RuntimeError("OpenAI disabled for this run.")
        except Exception as exc:
            copy = fallback_social_copy(item["novel"], abbr, item["day"], item["filename"])
            copy["warning"] = str(exc)
    if agent_meta is not None:
        agent_meta["_agent_used"] = agent_consumed
        if agent_consumed:
            agent_meta.setdefault("_agent_source", (agent_copy or {}).get("_source"))
    focus = resolve_post_focus(abbr, f"daily_{item['day']}", post_focus, chapter=chapter_number)
    if not agent_consumed:
        cta = focused_social_cta(abbr, focus)
        style = str(copy.get("caption_style") or rotating_caption_style(abbr, f"daily_{item['day']}_{focus}_{chapter_number or 'general'}"))
        daily_hook = {
            "scene_hook": f"{item['novel']} has another scene worth stepping into today.",
            "reader_question": "Would you read ahead if the next choice changed the whole path?",
            "stakes": f"The stakes are moving again in {item['novel']}.",
            "character_moment": f"Today's spotlight leans into a character turn from {item['novel']}.",
            "worldbuilding": f"Today's post opens another door into the world of {item['novel']}.",
            "catch_up": f"This is a good day to catch up on {item['novel']} before the next release.",
        }.get(style, f"{item['novel']} has another update ready.")
        base_instagram = str(copy.get("instagram", "")).strip()
        if daily_hook and daily_hook not in base_instagram:
            base_instagram = f"{daily_hook}\n\n{base_instagram}" if base_instagram else daily_hook
        if cta not in base_instagram:
            base_instagram = f"{base_instagram}\n\n{cta}" if base_instagram else cta
        copy["instagram"] = promo_copy_module.public_copy_without_links(with_instagram_links(base_instagram, abbr), "instagram")
        copy["x"] = str(copy.get("x") or fallback_social_copy(item["novel"], abbr, item["day"], item["filename"])["x"]).strip()
        x_focus_link = "Read now: link in bio."
        if "link in bio" not in copy["x"].lower():
            candidate = f"{copy['x']}\n{x_focus_link}".strip()
            copy["x"] = candidate if len(candidate) <= 275 else copy["x"]
        copy["x"] = promo_copy_module.public_copy_without_links(copy["x"], "x")
        copy["facebook"] = str(copy.get("facebook") or "").strip()
        if not copy["facebook"]:
            copy["facebook"] = "\n\n".join(
                [
                    f"{item['day']} spotlight: {item['novel']}.",
                    cta,
                    "Follow the story updates across the main channels.",
                    promo_copy_module.audience_hub_line(abbr),
                    "#webnovel #royalroad #serialfiction #indieauthor",
                ]
            )
        else:
            if cta not in copy["facebook"]:
                copy["facebook"] = f"{copy['facebook']}\n\n{cta}"
            if "link in bio" not in copy["facebook"].lower():
                copy["facebook"] = f"{copy['facebook']}\n\n{promo_copy_module.audience_hub_line(abbr)}"
        copy["facebook"] = promo_copy_module.public_copy_without_links(copy["facebook"], "facebook")
        copy["caption_style"] = style
    else:
        # Agent-differentiated copy is already final (assembled by build_platform_posts).
        # Only ensure the alt_text and caption_style fields are present and consistent.
        copy["alt_text"] = copy.get("alt_text") or f"Promotional image for {item['novel']}, scheduled for {item['day']}."
        copy.setdefault("caption_style", "")

    image_target = folder / f"{abbr}_{item['day']}.png"
    image_source = _get(collab, "create_fresh_social_image_from_caption")(
        image_target,
        abbr=abbr,
        novel=item["novel"],
        title=f"{item['novel']} {item['day']} social post",
        caption=copy["instagram"],
        hook=copy.get("x", ""),
        index=DAYS.index(item["day"]) + 1 if item["day"] in DAYS else 1,
    )
    copy["image_source"] = image_source

    payload = {
        **item,
        **copy,
        "source": source,
        "folder": str(folder),
        "image": str(image_target),
        "prompt_template": prompt_template,
        "post_focus": focus,
    }
    if str(chapter_number).strip():
        payload["chapter"] = str(chapter_number).strip()
    if agent_meta:
        for _k, _v in agent_meta.items():
            if str(_k).startswith("_agent_"):
                payload[_k] = _v
    (folder / "instagram.txt").write_text(copy["instagram"].strip() + "\n", encoding="utf-8")
    (folder / "x.txt").write_text(copy["x"].strip() + "\n", encoding="utf-8")
    (folder / "facebook.txt").write_text(copy["facebook"].strip() + "\n", encoding="utf-8")
    (folder / "alt-text.txt").write_text(copy["alt_text"].strip() + "\n", encoding="utf-8")
    (folder / "prompt-template.txt").write_text(prompt_template.strip() + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if str(chapter_number).strip():
        try:
            _get(collab, "update_chapter_ledger")(
                abbr,
                str(chapter_number).strip(),
                {
                    "socialPostsBuilt": True,
                    "dailySocialBuilt": True,
                    "dailySocialBuiltAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "dailySocialFolder": str(folder),
                    "folders": {"social": str(folder)},
                },
            )
        except Exception:
            pass
    try:
        (folder / "social-post-record.json").write_text(
            json.dumps(
                {
                    "contentType": "daily-social-post",
                    "platform": "multi-social",
                    "platforms": ["instagram", "x", "facebook"],
                    "platformStatus": {
                        "instagram": "draft",
                        "x": "manual-draft",
                        "facebook": "manual-draft",
                    },
                    "novel": payload.get("novel") or item.get("novel") or "",
                    "chapter": payload.get("chapter") or item.get("chapter_number") or "",
                    "title": payload.get("title") or item.get("filename") or "",
                    "publishDate": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "liveUrl": "",
                    "assetFolder": str(folder),
                    "folder": str(folder),
                    "instagram": payload.get("instagram", ""),
                    "x": payload.get("x", ""),
                    "facebook": payload.get("facebook", ""),
                    "agentMeta": {_k: _v for _k, _v in payload.items() if str(_k).startswith("_agent_")},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return _get(collab, "auto_publish_generated_media")(folder, payload)


def build_week_social_posts(use_openai: bool = False, days: list[str] | None = None,
                            *, collaborators: dict[str, Any] | None = None,
                            agent_copy_for: "Callable[[str, str, str, dict], tuple[dict | None, dict | None]] | None" = None) -> dict[str, Any]:
    collab = collaborators if collaborators is not None else _COLLAB
    selected_days = days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    posts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    template = SOCIAL_PROMPT_FILE.read_text(encoding="utf-8") if SOCIAL_PROMPT_FILE.exists() else "{novel} {day}"
    for day in selected_days:
        for abbr in NOVEL_NAMES:
            try:
                _agent_copy = None
                _agent_meta: dict[str, Any] | None = None
                if callable(agent_copy_for):
                    try:
                        _agent_copy, _agent_meta = agent_copy_for(abbr, day, template, {
                            "abbr": abbr,
                            "novel": NOVEL_NAMES.get(abbr, abbr),
                            "day": day,
                        })
                    except Exception:
                        _agent_copy, _agent_meta = None, None
                posts.append(make_social_post(
                    abbr, day, template, use_openai,
                    agent_copy=_agent_copy, agent_meta=_agent_meta, collaborators=collab,
                ))
            except Exception as exc:
                errors.append({"abbr": abbr, "day": day, "error": str(exc)})
    return {
        "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "days": selected_days,
        "posts": posts,
        "errors": errors,
        "count": len(posts),
    }
