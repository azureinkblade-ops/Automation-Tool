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
from typing import Any

import app_config as config
import promo_copy as copy

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
    "prepare_tiktok_outro_image",# side-effect: writes outro image
    "tiktok_chapter_teaser_overlays",  # pure: overlay list
    "write_tiktok_video_helper", # side-effect: ffmpeg video
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


def _get(collab: dict[str, Any], name: str):
    fn = collab.get(name)
    if fn is None:
        fn = _stub_raise(name)
    return fn


def make_tiktok_pack(
    abbr: str,
    chapter: str | None = None,
    force_new_images: bool = False,
    visual_prompt: str = "",
    chapter_text: str = "",
    style: str = "main-posts",
    *,
    collaborators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collab = collaborators or _default_collaborators()
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
        reused["caption"] = _get(collab, "tiktok_caption")(novel, group["chapter"])
        reused["instagram_reel_caption"] = _get(collab, "instagram_reel_caption")(novel, group["chapter"])
        shorts = _get(collab, "youtube_shorts_metadata")(novel, group["chapter"])
        reused["youtube_shorts_title"] = shorts["title"]
        reused["youtube_shorts_description"] = shorts["description"]
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
            _get(collab, "write_tiktok_video_helper")(folder, image_files[:4], sound_path, overlays=overlays)
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
    caption = _get(collab, "tiktok_caption")(novel, group["chapter"])
    reel_caption = _get(collab, "instagram_reel_caption")(novel, group["chapter"])
    shorts = _get(collab, "youtube_shorts_metadata")(novel, group["chapter"])
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
        "youtube_shorts_title": shorts["title"],
        "youtube_shorts_description": shorts["description"],
        "folder": str(folder),
        "visual_prompt": visual_prompt,
        "video_overlays": overlays,
    }
    (folder / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    (folder / "instagram-reel-caption.txt").write_text(reel_caption + "\n", encoding="utf-8")
    (folder / "youtube-shorts-title.txt").write_text(shorts["title"] + "\n", encoding="utf-8")
    (folder / "youtube-shorts-description.txt").write_text(shorts["description"] + "\n", encoding="utf-8")
    (folder / "sound.txt").write_text(str(sound_target) + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _get(collab, "write_tiktok_video_helper")(folder, copied_images, sound_target, overlays=overlays)
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
    *,
    collaborators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collab = collaborators or _default_collaborators()
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
    focus = resolve_post_focus(abbr, f"daily_{item['day']}", post_focus, chapter=chapter_number)
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
    copy["instagram"] = with_instagram_links(base_instagram, abbr)
    copy["x"] = str(copy.get("x") or fallback_social_copy(item["novel"], abbr, item["day"], item["filename"])["x"]).strip()
    x_focus_link = linktree_url()
    if x_focus_link and x_focus_link not in copy["x"]:
        candidate = f"{copy['x']}\n{x_focus_link}".strip()
        copy["x"] = candidate if len(candidate) <= 275 else copy["x"]
    copy["facebook"] = str(copy.get("facebook") or "").strip()
    if not copy["facebook"]:
        copy["facebook"] = "\n\n".join(
            [
                f"{item['day']} spotlight: {item['novel']}.",
                cta,
                "Follow the story updates across the main channels.",
                platform_links_block(abbr),
                "#webnovel #royalroad #serialfiction #indieauthor",
            ]
        )
    else:
        if cta not in copy["facebook"]:
            copy["facebook"] = f"{copy['facebook']}\n\n{cta}"
        if linktree_url() not in copy["facebook"]:
            copy["facebook"] = f"{copy['facebook']}\n\n{platform_links_block(abbr)}"
    copy["caption_style"] = style

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
    return _get(collab, "auto_publish_generated_media")(folder, payload)


def build_week_social_posts(use_openai: bool = False, days: list[str] | None = None,
                            *, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    collab = collaborators or _default_collaborators()
    selected_days = days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    posts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    template = SOCIAL_PROMPT_FILE.read_text(encoding="utf-8") if SOCIAL_PROMPT_FILE.exists() else "{novel} {day}"
    for day in selected_days:
        for abbr in NOVEL_NAMES:
            try:
                posts.append(make_social_post(abbr, day, template, use_openai, collaborators=collab))
            except Exception as exc:
                errors.append({"abbr": abbr, "day": day, "error": str(exc)})
    return {
        "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "days": selected_days,
        "posts": posts,
        "errors": errors,
        "count": len(posts),
    }
