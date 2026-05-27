from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "campaigns"
ASSET_DIR = ROOT / "assets"
ENV_FILE = ROOT / ".env.local"
PORT = int(os.environ.get("AUTOMATION_TOOL_PORT", "8765"))
BACKGROUND_VIDEO_DIR = Path(os.environ.get("BACKGROUND_VIDEO_DIR", r"C:\Users\David\Documents\Novels"))
CLOUDFLARE_MEDIA_DIR = Path(os.environ.get("CLOUDFLARE_MEDIA_DIR", r"C:\Users\David\Documents\CloudFlare"))
PROMO_IMAGES_DIR = Path(os.environ.get("PROMO_IMAGES_DIR", str(CLOUDFLARE_MEDIA_DIR if CLOUDFLARE_MEDIA_DIR.exists() else Path(r"C:\Users\David\Documents\Promo Images"))))
TIKTOK_ASSET_DIR = Path(os.environ.get("TIKTOK_ASSET_DIR", str(CLOUDFLARE_MEDIA_DIR if CLOUDFLARE_MEDIA_DIR.exists() else PROMO_IMAGES_DIR / "TIkTok")))
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
LOCAL_FFMPEG_DIR = ROOT / "tools" / "ffmpeg"
SOCIAL_OUTPUT_DIR = ROOT / "social-posts"
TIKTOK_OUTPUT_DIR = ROOT / "tiktok-posts"
CHAPTER_OUTPUT_DIR = ROOT / "chapters"
YOUTUBE_OUTPUT_DIR = ROOT / "youtube-videos"
GITHUB_MEDIA_DIR = ROOT / "docs" / "media"
GITHUB_REMOTE_URL = os.environ.get("GITHUB_REMOTE_URL", "https://github.com/azureinkblade-ops/Automation-tool.git")
DEFAULT_GITHUB_PAGES_MEDIA_BASE_URL = "https://azureinkblade-ops.github.io/Automation-tool/media"
META_GRAPH_API_VERSION = os.environ.get("META_GRAPH_API_VERSION", "v25.0")
NOVEL_NAMES = {
    "EN": "Eternal Nexus",
    "HA": "Heavenly Ascension System",
    "SF": "Soul Forge Era",
    "HP": "Hundredfold Path",
}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CHAPTER_RELEASE_DAYS = ["Monday", "Wednesday", "Friday", "Sunday"]
GENERAL_PROMO_DAYS = ["Tuesday", "Thursday", "Saturday"]
SCHEDULE_FILE = ROOT / "posting_schedule.json"


def find_ffmpeg_executable() -> str:
    configured = os.environ.get("FFMPEG_EXE")
    if configured and Path(configured).exists():
        return configured
    local = LOCAL_FFMPEG_DIR / "bin" / "ffmpeg.exe"
    if local.exists():
        return str(local)
    tools = ROOT / "tools"
    if tools.exists():
        for path in tools.rglob("ffmpeg.exe"):
            return str(path)
    return "ffmpeg"


def load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def env_presence() -> dict[str, bool]:
    return {
        "instagramAccountId": bool(os.environ.get("INSTAGRAM_ACCOUNT_ID")),
        "instagramAccessToken": bool(os.environ.get("INSTAGRAM_ACCESS_TOKEN")),
        "instagramPublicBaseUrl": bool(os.environ.get("INSTAGRAM_PUBLIC_BASE_URL")),
        "xAccessToken": bool(os.environ.get("X_ACCESS_TOKEN")),
        "bufferApiKey": bool(os.environ.get("BUFFER_API_KEY")),
        "bufferPublicBaseUrl": bool(os.environ.get("BUFFER_PUBLIC_BASE_URL")),
        "bufferChannelIds": bool(os.environ.get("BUFFER_CHANNEL_IDS")),
        "bufferChannelIdCount": len([value for value in os.environ.get("BUFFER_CHANNEL_IDS", "").split(",") if value.strip()]),
        "r2AccountId": bool(os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID")),
        "r2AccessKeyId": bool(os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")),
        "r2SecretAccessKey": bool(os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")),
        "r2Bucket": bool(os.environ.get("CLOUDFLARE_R2_BUCKET")),
        "r2PublicBaseUrl": bool(os.environ.get("CLOUDFLARE_R2_PUBLIC_BASE_URL")),
        "githubPagesMediaBaseUrl": bool(github_pages_media_base_url()),
        "githubAutoPublishMedia": github_auto_publish_media(),
        "githubToken": bool(os.environ.get("GITHUB_TOKEN")),
        "openaiApiKey": bool(os.environ.get("OPENAI_API_KEY")),
    }


def upsert_env_values(values: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                existing[key.strip()] = value.strip()
    for key, value in values.items():
        if value:
            existing[key] = value
            os.environ[key] = value
    ordered = [
        "OPENAI_API_KEY",
        "INSTAGRAM_ACCOUNT_ID",
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_PUBLIC_BASE_URL",
        "META_GRAPH_API_VERSION",
        "X_ACCESS_TOKEN",
        "BUFFER_API_KEY",
        "BUFFER_PUBLIC_BASE_URL",
        "BUFFER_CHANNEL_IDS",
        "CLOUDFLARE_R2_ACCOUNT_ID",
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_BUCKET",
        "CLOUDFLARE_R2_PUBLIC_BASE_URL",
        "GITHUB_PAGES_MEDIA_BASE_URL",
        "GITHUB_REMOTE_URL",
        "GITHUB_TOKEN",
        "GITHUB_AUTO_PUBLISH_MEDIA",
        "BACKGROUND_VIDEO_DIR",
        "PROMO_IMAGES_DIR",
    ]
    lines: list[str] = []
    for key in ordered:
        if key in existing:
            lines.append(f"{key}={existing[key]}")
    for key, value in existing.items():
        if key not in ordered:
            lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def normalize_public_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    if not value.lower().startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:70] or "chapter"


def iso_today() -> date:
    return date.today()


def ensure_schedule_file() -> dict[str, Any]:
    if SCHEDULE_FILE.exists():
        return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
    today = iso_today()
    config = {
        "chapterReleaseDays": CHAPTER_RELEASE_DAYS,
        "generalPromoDays": GENERAL_PROMO_DAYS,
        "royalRoadDelayDays": 14,
        "generalPromoRotation": ["YouTube", "Royal Road", "TikTok"],
        "novels": [
            {
                "abbr": abbr,
                "name": name,
                "nextChapter": 1,
                "startDate": today.isoformat(),
                "releaseDays": CHAPTER_RELEASE_DAYS,
            }
            for abbr, name in NOVEL_NAMES.items()
        ],
    }
    SCHEDULE_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def next_dates(start: date, day_names: list[str], count: int) -> list[date]:
    results: list[date] = []
    cursor = start
    wanted = set(day_names)
    while len(results) < count:
        if cursor.strftime("%A") in wanted:
            results.append(cursor)
        cursor += timedelta(days=1)
    return results


def platform_copy(platform: str, novel: str, chapter: int, release_date: date, target: str) -> dict[str, str]:
    if platform == "chapter":
        if target == "Patreon":
            instagram = (
                f"New chapter for {novel} is live on Patreon.\n\n"
                f"Chapter {chapter} is available now for early readers.\n\n"
                "#webnovel #patreon #booktok #indieauthor"
            )
            x_text = f"{novel} Chapter {chapter} is live on Patreon for early readers. #webnovel #Patreon"
        else:
            instagram = (
                f"{novel} Chapter {chapter} is now live on Royal Road.\n\n"
                "Catch up with the latest public release today.\n\n"
                "#royalroad #webnovel #booktok #progressionfantasy"
            )
            x_text = f"{novel} Chapter {chapter} is now live on Royal Road. #RoyalRoad #webnovel"
    else:
        instagram = (
            f"{release_date.strftime('%A')} spotlight for {novel}.\n\n"
            f"Today is a good day to catch the story on {target}.\n\n"
            "#webnovel #booktok #indieauthor #fantasybooks"
        )
        x_text = f"{release_date.strftime('%A')} spotlight: catch {novel} on {target}. #webnovel #booktok"
    if len(x_text) > 260:
        x_text = x_text[:257].rsplit(" ", 1)[0] + "..."
    return {"instagram": instagram, "x": x_text}


def build_schedule(days_ahead: int = 28) -> list[dict[str, Any]]:
    config = ensure_schedule_file()
    start = iso_today()
    end = start + timedelta(days=days_ahead)
    tasks: list[dict[str, Any]] = []
    rotation = config.get("generalPromoRotation") or ["YouTube", "Royal Road", "TikTok"]
    delay = int(config.get("royalRoadDelayDays", 14))

    for novel in config.get("novels", []):
        abbr = novel["abbr"]
        name = novel["name"]
        next_chapter = int(novel.get("nextChapter", 1))
        start_date = datetime.fromisoformat(novel.get("startDate", start.isoformat())).date()
        release_days = novel.get("releaseDays") or CHAPTER_RELEASE_DAYS
        release_dates = next_dates(start_date, release_days, 120)
        for index, patreon_date in enumerate(release_dates):
            chapter = next_chapter + index
            royal_date = patreon_date + timedelta(days=delay)
            if start <= patreon_date <= end:
                copy = platform_copy("chapter", name, chapter, patreon_date, "Patreon")
                tasks.append(
                    {
                        "date": patreon_date.isoformat(),
                        "day": patreon_date.strftime("%A"),
                        "type": "chapter",
                        "platform": "Patreon",
                        "abbr": abbr,
                        "novel": name,
                        "chapter": chapter,
                        **copy,
                    }
                )
            if start <= royal_date <= end:
                copy = platform_copy("chapter", name, chapter, royal_date, "Royal Road")
                tasks.append(
                    {
                        "date": royal_date.isoformat(),
                        "day": royal_date.strftime("%A"),
                        "type": "chapter",
                        "platform": "Royal Road",
                        "abbr": abbr,
                        "novel": name,
                        "chapter": chapter,
                        **copy,
                    }
                )

        promo_dates = next_dates(start, GENERAL_PROMO_DAYS, days_ahead)
        novel_offset = list(NOVEL_NAMES.keys()).index(abbr) if abbr in NOVEL_NAMES else 0
        for index, promo_date in enumerate(promo_dates):
            if promo_date > end:
                continue
            target = rotation[(index + novel_offset) % len(rotation)]
            copy = platform_copy("promo", name, 0, promo_date, target)
            tasks.append(
                {
                    "date": promo_date.isoformat(),
                    "day": promo_date.strftime("%A"),
                    "type": "promo",
                    "platform": target,
                    "abbr": abbr,
                    "novel": name,
                    "chapter": None,
                    **copy,
                }
            )

    tasks.sort(key=lambda item: (item["date"], item["abbr"], item["platform"]))
    return tasks


def schedule_tasks_for(date_text: str | None = None) -> list[dict[str, Any]]:
    target = datetime.fromisoformat(date_text).date() if date_text else iso_today()
    return [task for task in build_schedule(35) if task["date"] == target.isoformat()]


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    size = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(size).decode("utf-8")
    return json.loads(raw or "{}")


def sentence_split(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if len(part.strip()) > 35]


def score_sentence(sentence: str) -> int:
    drama = {
        "blood",
        "dark",
        "secret",
        "death",
        "monster",
        "magic",
        "sword",
        "heart",
        "fire",
        "shadow",
        "betray",
        "king",
        "queen",
        "war",
        "kiss",
        "fear",
        "truth",
        "danger",
        "promise",
        "curse",
    }
    words = re.findall(r"[a-zA-Z']+", sentence.lower())
    return len(set(words) & drama) * 4 + min(len(words), 28)


def fallback_phrases(chapter: str) -> list[str]:
    sentences = sentence_split(chapter)
    if not sentences:
        return ["A new chapter begins", "The truth refuses to stay buried", "Everything changes now"]
    ranked = sorted(sentences, key=score_sentence, reverse=True)
    phrases: list[str] = []
    for sentence in ranked:
        phrase = re.sub(r"\s+", " ", sentence).strip()
        if len(phrase) > 115:
            phrase = phrase[:112].rsplit(" ", 1)[0] + "..."
        if phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) == 3:
            break
    while len(phrases) < 3:
        phrases.append("A moment readers will not forget")
    return phrases


def fallback_caption(title: str, phrases: list[str]) -> str:
    return "\n".join(
        [
            f"{title or 'New chapter'} is live.",
            "",
            phrases[0],
            "",
            "Read the chapter now on Royal Road or Patreon.",
            "#webnovel #royalroad #patreon #writingcommunity #booktok",
        ]
    )


def default_social_prompt() -> str:
    return textwrap.dedent(
        """
        Create reusable social copy for a daily web-novel promo image.

        Inputs:
        Novel: {novel}
        Abbreviation: {abbr}
        Day: {day}
        Image filename: {filename}

        Return JSON with:
        - instagram: a polished Instagram caption, 1 hook line, 1 short value/teaser line, 1 call to action, and hashtags
        - x: a concise X post under 260 characters with 2-4 hashtags
        - alt_text: accessible image alt text

        Style:
        - web novel reader audience
        - energetic but not spammy
        - no fake chapter number unless one is supplied
        - mention the novel name naturally
        """
    ).strip()


def social_prompt_template() -> str:
    prompt_file = ROOT / "social_prompt_template.txt"
    if not prompt_file.exists():
        prompt_file.write_text(default_social_prompt() + "\n", encoding="utf-8")
    return prompt_file.read_text(encoding="utf-8")


def list_daily_promo_images() -> list[dict[str, str]]:
    if not PROMO_IMAGES_DIR.exists():
        return []
    items: list[dict[str, str]] = []
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    for path in sorted(PROMO_IMAGES_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in image_exts:
            continue
        match = re.match(r"^([A-Z]{2})_([A-Za-z]+)", path.stem)
        if not match:
            continue
        abbr, day = match.group(1), match.group(2)
        if day not in DAYS:
            continue
        items.append(
            {
                "abbr": abbr,
                "novel": NOVEL_NAMES.get(abbr, abbr),
                "day": day,
                "filename": path.name,
                "path": str(path),
            }
        )
    return items


def list_tiktok_assets() -> dict[str, Any]:
    if not TIKTOK_ASSET_DIR.exists():
        return {"sounds": [], "imageGroups": [], "videos": []}
    sounds = [path for path in sorted(TIKTOK_ASSET_DIR.iterdir()) if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS]
    videos = [path for path in sorted(TIKTOK_ASSET_DIR.iterdir()) if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
    groups: dict[tuple[str, str], list[Path]] = {}
    for path in sorted(TIKTOK_ASSET_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        match = re.match(r"^([A-Z]{2})_(\d+)_([123])$", path.stem)
        if not match:
            continue
        groups.setdefault((match.group(1), match.group(2)), []).append(path)
    image_groups = [
        {
            "abbr": abbr,
            "novel": NOVEL_NAMES.get(abbr, abbr),
            "chapter": chapter,
            "count": len(paths),
            "files": [str(path) for path in paths],
        }
        for (abbr, chapter), paths in sorted(groups.items(), key=lambda item: (item[0][0], int(item[0][1])))
    ]
    return {
        "sounds": [{"name": path.name, "path": str(path)} for path in sounds],
        "imageGroups": image_groups,
        "videos": [{"name": path.name, "path": str(path)} for path in videos],
    }


def tiktok_caption(novel: str, chapter: str) -> str:
    chapter_text = f" Chapter {chapter}" if chapter else ""
    tags = {
        "Eternal Nexus": "#EternalNexus #booktok #webnovel #scififantasy",
        "Heavenly Ascension System": "#HeavenlyAscensionSystem #booktok #cultivation #litrpg",
        "Soul Forge Era": "#SoulForgeEra #booktok #progressionfantasy #webnovel",
        "Hundredfold Path": "#HundredfoldPath #booktok #litrpg #webnovel",
    }.get(novel, "#booktok #webnovel #royalroad")
    return f"{novel}{chapter_text} is waiting. Read the story and follow for the next drop. {tags}"


def make_tiktok_pack(abbr: str, chapter: str | None = None) -> dict[str, Any]:
    assets = list_tiktok_assets()
    groups = [group for group in assets["imageGroups"] if group["abbr"] == abbr]
    if chapter:
        groups = [group for group in groups if group["chapter"] == str(chapter)]
    if not groups:
        raise RuntimeError(f"No TikTok image group found for {abbr}{' chapter ' + str(chapter) if chapter else ''}.")
    group = groups[-1] if not chapter else groups[0]
    sounds = assets["sounds"]
    if not sounds:
        raise RuntimeError("No TikTok sound files were found.")
    sound = random.choice(sounds)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    folder = TIKTOK_OUTPUT_DIR / f"{timestamp}-{abbr.lower()}-{group['chapter']}"
    folder.mkdir(parents=True, exist_ok=True)
    copied_images: list[str] = []
    for image in group["files"][:3]:
        source = Path(image)
        target = folder / source.name
        shutil.copy2(source, target)
        copied_images.append(str(target))
    sound_source = Path(sound["path"])
    sound_target = folder / sound_source.name
    shutil.copy2(sound_source, sound_target)
    novel = NOVEL_NAMES.get(abbr, abbr)
    caption = tiktok_caption(novel, group["chapter"])
    payload = {
        "abbr": abbr,
        "novel": novel,
        "chapter": group["chapter"],
        "images": copied_images,
        "sound": str(sound_target),
        "caption": caption,
        "folder": str(folder),
    }
    (folder / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    (folder / "sound.txt").write_text(str(sound_target) + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_tiktok_video_helper(folder, copied_images, sound_target)
    return auto_publish_generated_media(folder, payload)


def generate_tiktok_images(abbr: str, chapter: str, visual_prompt: str) -> dict[str, Any]:
    TIKTOK_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    novel = NOVEL_NAMES.get(abbr, abbr)
    prompt_base = visual_prompt.strip() or f"{novel} chapter {chapter}, cinematic web novel promo art"
    created: list[str] = []
    for index in range(1, 4):
        target = TIKTOK_ASSET_DIR / f"{abbr}_{chapter}_{index}.png"
        prompt = (
            f"Vertical TikTok promo image {index} for {novel} chapter {chapter}. "
            f"{prompt_base}. Cinematic, dramatic, readable composition, no text, 9:16 poster art."
        )
        try:
            create_openai_image(prompt, target)
        except Exception:
            placeholder = ASSET_DIR / "placeholder.svg"
            svg_target = TIKTOK_ASSET_DIR / f"{abbr}_{chapter}_{index}.svg"
            text = placeholder.read_text(encoding="utf-8").replace("{{PHRASE}}", f"{novel} Chapter {chapter}")
            svg_target.write_text(text, encoding="utf-8")
            target = svg_target
        created.append(str(target))
    return {"created": created, "abbr": abbr, "chapter": chapter, "folder": str(TIKTOK_ASSET_DIR)}


def make_or_generate_tiktok_pack(abbr: str, chapter: str, visual_prompt: str = "") -> dict[str, Any]:
    if not abbr or not str(chapter).strip():
        raise RuntimeError("Choose a novel and enter a chapter number for TikTok.")
    assets = list_tiktok_assets()
    exists = any(group["abbr"] == abbr and group["chapter"] == str(chapter) for group in assets["imageGroups"])
    if not exists:
        generate_tiktok_images(abbr, str(chapter), visual_prompt)
    return make_tiktok_pack(abbr, str(chapter))


def write_tiktok_video_helper(folder: Path, images: list[str], sound: Path) -> None:
    ffmpeg_exe = find_ffmpeg_executable()
    script = folder / "make_tiktok_video.py"
    script.write_text(
        f'''from pathlib import Path
import subprocess

folder = Path(__file__).resolve().parent
images = {[Path(image).name for image in images]!r}
sound = folder / {sound.name!r}
ffmpeg_exe = {ffmpeg_exe!r}
output = folder / "tiktok-video.mp4"

concat = folder / "tiktok-slides.txt"
concat.write_text("\\n".join([f"file '{{folder / image}}'\\nduration 3" for image in images] + [f"file '{{folder / images[-1]}}'"]) + "\\n", encoding="utf-8")

subprocess.run([
    ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
    "-i", str(sound), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
    "-shortest", "-pix_fmt", "yuv420p", str(output)
], check=False)

print(f"TikTok video target: {{output}}")
''',
        encoding="utf-8",
    )


def fallback_social_copy(novel: str, abbr: str, day: str, filename: str) -> dict[str, str]:
    tags = {
        "Eternal Nexus": "#EternalNexus #webnovel #scifi #fantasybooks #royalroad",
        "Heavenly Ascension System": "#HeavenlyAscensionSystem #cultivation #litrpg #webnovel #royalroad",
        "Soul Forge Era": "#SoulForgeEra #fantasybooks #progressionfantasy #webnovel #booktok",
        "Hundredfold Path": "#HundredfoldPath #progressionfantasy #litrpg #webnovel #indieauthor",
    }.get(novel, "#webnovel #royalroad #indieauthor #booktok")
    instagram = "\n".join(
        [
            f"{day} spotlight: {novel}.",
            "A new reason to step into the story today.",
            "Read now on Royal Road, and follow for the next update.",
            "",
            tags,
        ]
    )
    x_text = f"{day} spotlight for {novel}. Step into the story today. Read now on Royal Road. {tags.split()[0]} #webnovel"
    if len(x_text) > 260:
        x_text = x_text[:257].rsplit(" ", 1)[0] + "..."
    return {
        "instagram": instagram,
        "x": x_text,
        "alt_text": f"Promotional image for {novel}, scheduled for {day}.",
    }


def social_copy_with_openai(prompt_template: str, novel: str, abbr: str, day: str, filename: str) -> dict[str, str]:
    prompt = prompt_template.format(novel=novel, abbr=abbr, day=day, filename=filename)
    result = openai_request(
        "chat/completions",
        {
            "model": os.environ.get("OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
            "messages": [
                {"role": "system", "content": "You write compact, reusable social media copy. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.75,
            "response_format": {"type": "json_object"},
        },
    )
    return json.loads(result["choices"][0]["message"]["content"])


def make_social_post(abbr: str, day: str, prompt_template: str, use_openai: bool) -> dict[str, Any]:
    matches = [
        item
        for item in list_daily_promo_images()
        if item["abbr"] == abbr and item["day"].lower() == day.lower()
    ]
    if not matches:
        raise RuntimeError(f"No daily promo image found for {abbr} {day}.")
    item = matches[0]
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    folder = SOCIAL_OUTPUT_DIR / f"{timestamp}-{abbr.lower()}-{item['day'].lower()}"
    folder.mkdir(parents=True, exist_ok=True)
    image_source = Path(item["path"])
    image_target = folder / image_source.name
    shutil.copy2(image_source, image_target)

    source = "fallback"
    try:
        if use_openai:
            copy = social_copy_with_openai(prompt_template, item["novel"], abbr, item["day"], item["filename"])
            source = "openai"
        else:
            raise RuntimeError("OpenAI disabled for this run.")
    except Exception as exc:
        copy = fallback_social_copy(item["novel"], abbr, item["day"], item["filename"])
        copy["warning"] = str(exc)

    payload = {
        **item,
        **copy,
        "source": source,
        "folder": str(folder),
        "image": str(image_target),
        "prompt_template": prompt_template,
    }
    (folder / "instagram.txt").write_text(copy["instagram"].strip() + "\n", encoding="utf-8")
    (folder / "x.txt").write_text(copy["x"].strip() + "\n", encoding="utf-8")
    (folder / "alt-text.txt").write_text(copy["alt_text"].strip() + "\n", encoding="utf-8")
    (folder / "prompt-template.txt").write_text(prompt_template.strip() + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return auto_publish_generated_media(folder, payload)


def openai_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.openai.com/v1/{path}",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def form_request(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def graph_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/{path}?{query}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def bearer_json_request(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def buffer_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Buffer is not configured. Add BUFFER_API_KEY in Connections.")
    data = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        "https://api.buffer.com",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload


def buffer_connection_diagnostics() -> dict[str, Any]:
    key_saved = bool(os.environ.get("BUFFER_API_KEY", "").strip())
    diagnostics: dict[str, Any] = {
        "keySaved": key_saved,
        "networkReachable": False,
        "authenticated": False,
        "channelCount": 0,
        "channels": [],
    }
    if not key_saved:
        diagnostics["error"] = "No Buffer API key is saved."
        return diagnostics
    try:
        account = buffer_graphql(
            """
            query Account {
              account { id email organizations { id name } }
            }
            """
        )
        diagnostics["networkReachable"] = True
        diagnostics["authenticated"] = True
        diagnostics["account"] = account.get("data", {}).get("account", {})
        try:
            channels = buffer_channels().get("channels", [])
        except Exception as exc:
            diagnostics["channelLookupError"] = str(exc)
            channels = configured_buffer_channels()
        if not channels:
            saved_channels = configured_buffer_channels()
            if saved_channels:
                diagnostics["channelLookupFallback"] = "saved"
                channels = saved_channels
        diagnostics["channels"] = channels
        diagnostics["channelCount"] = len(channels)
        return diagnostics
    except urllib.error.HTTPError as exc:
        diagnostics["networkReachable"] = True
        diagnostics["errorType"] = "http"
        diagnostics["status"] = exc.code
        diagnostics["error"] = exc.read().decode("utf-8", errors="replace")
        if diagnostics.get("authenticated"):
            channels = configured_buffer_channels()
            diagnostics["channels"] = channels
            diagnostics["channelCount"] = len(channels)
            diagnostics["channelLookupFallback"] = "saved"
        return diagnostics
    except urllib.error.URLError as exc:
        diagnostics["errorType"] = "network"
        diagnostics["error"] = str(exc)
        if diagnostics.get("authenticated"):
            channels = configured_buffer_channels()
            diagnostics["channels"] = channels
            diagnostics["channelCount"] = len(channels)
            diagnostics["channelLookupFallback"] = "saved"
        return diagnostics
    except Exception as exc:
        diagnostics["networkReachable"] = True
        diagnostics["errorType"] = "application"
        diagnostics["error"] = str(exc)
        return diagnostics


def powershell_buffer_test() -> dict[str, Any]:
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        return {"keySaved": False, "error": "No Buffer API key is saved."}
    query = '{ "query": "query Account { account { id email organizations { id name } } }" }'
    ps = f"""
$Headers = @{{ Authorization = 'Bearer {key}'; 'Content-Type' = 'application/json' }}
$Body = @'
{query}
'@
try {{
  $Result = Invoke-RestMethod -Uri 'https://api.buffer.com' -Method Post -Headers $Headers -Body $Body
  $Result | ConvertTo-Json -Depth 20
}} catch {{
  $_.Exception.Message
  if ($_.ErrorDetails) {{ $_.ErrorDetails.Message }}
  exit 1
}}
"""
    run = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=120)
    if run.returncode != 0:
        return {"keySaved": True, "networkReachable": False, "authenticated": False, "error": (run.stdout + run.stderr).strip()}
    try:
        payload = json.loads(run.stdout)
    except Exception:
        return {"keySaved": True, "networkReachable": True, "authenticated": False, "raw": run.stdout}
    if payload.get("errors"):
        return {"keySaved": True, "networkReachable": True, "authenticated": False, "error": payload["errors"]}
    return {"keySaved": True, "networkReachable": True, "authenticated": True, "account": payload.get("data", {}).get("account", {})}


def buffer_channels() -> dict[str, Any]:
    account = buffer_graphql(
        """
        query Account {
          account {
            id
            organizations { id name }
          }
        }
        """
    )
    orgs = account.get("data", {}).get("account", {}).get("organizations", [])
    channels: list[dict[str, Any]] = []
    for org in orgs:
        result = buffer_graphql(
            """
            query Channels($organizationId: OrganizationId!) {
              channels(input: { organizationId: $organizationId }) {
                id
                name
                service
              }
            }
            """,
            {"organizationId": org["id"]},
        )
        for channel in result.get("data", {}).get("channels", []):
            channel["organizationId"] = org["id"]
            channel["organizationName"] = org.get("name", "")
            channels.append(channel)
    return {"organizations": orgs, "channels": channels}


def configured_buffer_channels() -> list[dict[str, str]]:
    ids = [value.strip() for value in os.environ.get("BUFFER_CHANNEL_IDS", "").split(",") if value.strip()]
    labels = [("instagram", "Instagram"), ("youtube", "YouTube"), ("tiktok", "TikTok")]
    channels: list[dict[str, str]] = []
    for index, channel_id in enumerate(ids):
        service, name = labels[index] if index < len(labels) else ("buffer", f"Buffer Channel {index + 1}")
        channels.append({"id": channel_id, "service": service, "name": name, "source": "saved"})
    return channels


def public_url_for_generated_file(path: Path) -> str | None:
    base = normalize_public_base_url(os.environ.get("BUFFER_PUBLIC_BASE_URL", ""))
    if not base:
        base = normalize_public_base_url(os.environ.get("CLOUDFLARE_R2_PUBLIC_BASE_URL", ""))
    if not base:
        base = normalize_public_base_url(os.environ.get("INSTAGRAM_PUBLIC_BASE_URL", ""))
    if not base:
        base = github_pages_media_base_url()
    if not base:
        return None
    resolved = path.resolve()
    roots = [SOCIAL_OUTPUT_DIR.resolve(), TIKTOK_OUTPUT_DIR.resolve(), OUTPUT_DIR.resolve(), CHAPTER_OUTPUT_DIR.resolve()]
    for root in roots:
        if str(resolved).startswith(str(root)):
            relative = resolved.relative_to(root).as_posix()
            return f"{base}/{urllib.parse.quote(relative, safe='/')}"
    return None


def github_pages_media_base_url() -> str:
    return normalize_public_base_url(
        os.environ.get("GITHUB_PAGES_MEDIA_BASE_URL", DEFAULT_GITHUB_PAGES_MEDIA_BASE_URL)
    )


def github_auto_publish_media() -> bool:
    value = os.environ.get("GITHUB_AUTO_PUBLISH_MEDIA", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def media_key_for_generated_file(path: Path) -> str:
    resolved = path.resolve()
    for root_name, root in [
        ("social-posts", SOCIAL_OUTPUT_DIR.resolve()),
        ("tiktok-posts", TIKTOK_OUTPUT_DIR.resolve()),
        ("campaigns", OUTPUT_DIR.resolve()),
        ("youtube-videos", YOUTUBE_OUTPUT_DIR.resolve()),
        ("chapters", CHAPTER_OUTPUT_DIR.resolve()),
    ]:
        if str(resolved).startswith(str(root)):
            return f"{root_name}/{resolved.relative_to(root).as_posix()}"
    return f"uploads/{path.name}"


def github_media_url_for_key(key: str) -> str:
    base = github_pages_media_base_url().rstrip("/")
    return f"{base}/{urllib.parse.quote(key, safe='/')}"


def github_repo_parts() -> tuple[str, str]:
    remote = os.environ.get("GITHUB_REMOTE_URL", GITHUB_REMOTE_URL).strip() or GITHUB_REMOTE_URL
    remote = remote.removesuffix(".git").rstrip("/")
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+)$", remote)
    if not match:
        raise RuntimeError("GITHUB_REMOTE_URL must point to a GitHub repository.")
    return match.group("owner"), match.group("repo")


def github_api_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Save a GitHub token in Connections first.")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "AutomationTool/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(path) from exc
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed: {detail}") from exc


def github_existing_sha(owner: str, repo: str, path: str, branch: str) -> str | None:
    encoded_path = urllib.parse.quote(path, safe="/")
    try:
        data = github_api_request("GET", f"/repos/{owner}/{repo}/contents/{encoded_path}?ref={urllib.parse.quote(branch)}")
    except FileNotFoundError:
        return None
    return str(data.get("sha") or "") or None


def upload_file_to_github(path: Path, repo_path: str, message: str) -> dict[str, Any]:
    owner, repo = github_repo_parts()
    branch = os.environ.get("GITHUB_BRANCH", "main").strip() or "main"
    sha = github_existing_sha(owner, repo, repo_path, branch)
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(path.read_bytes()).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    encoded_path = urllib.parse.quote(repo_path, safe="/")
    result = github_api_request("PUT", f"/repos/{owner}/{repo}/contents/{encoded_path}", payload)
    return {
        "path": repo_path,
        "sha": result.get("content", {}).get("sha", ""),
        "commit": result.get("commit", {}).get("sha", ""),
        "html_url": result.get("content", {}).get("html_url", ""),
    }


def publish_folder_media_to_github_api(folder: str) -> dict[str, Any]:
    copied = copy_folder_media_to_github(folder)
    uploaded = []
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    nojekyll = ROOT / "docs" / ".nojekyll"
    nojekyll.parent.mkdir(parents=True, exist_ok=True)
    nojekyll.touch(exist_ok=True)
    uploaded.append(upload_file_to_github(nojekyll, "docs/.nojekyll", f"Enable GitHub Pages media {timestamp}"))
    for item in copied.get("copied", []):
        local_path = Path(item["repo_path"])
        uploaded.append(
            upload_file_to_github(
                local_path,
                f"docs/media/{item['key']}",
                f"Publish automation media {timestamp}",
            )
        )
    return {**copied, "published": True, "method": "github-api", "uploaded": uploaded}


def r2_configured() -> bool:
    required = [
        "CLOUDFLARE_R2_ACCOUNT_ID",
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_BUCKET",
        "CLOUDFLARE_R2_PUBLIC_BASE_URL",
    ]
    return all(os.environ.get(key, "").strip() for key in required)


def signing_key(secret: str, date_stamp: str, region: str = "auto", service: str = "s3") -> bytes:
    key = ("AWS4" + secret).encode("utf-8")
    date_key = hmac.new(key, date_stamp.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def r2_object_key(path: Path) -> str:
    return media_key_for_generated_file(path)


def r2_public_url_for_key(key: str) -> str:
    base = normalize_public_base_url(os.environ["CLOUDFLARE_R2_PUBLIC_BASE_URL"])
    return f"{base}/{urllib.parse.quote(key, safe='/')}"


def upload_file_to_r2(path: Path) -> dict[str, str]:
    if not r2_configured():
        raise RuntimeError("Cloudflare R2 is not configured in Connections.")
    account_id = os.environ["CLOUDFLARE_R2_ACCOUNT_ID"].strip()
    access_key = os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"].strip()
    secret_key = os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"].strip()
    bucket = os.environ["CLOUDFLARE_R2_BUCKET"].strip()
    key = r2_object_key(path)
    body = path.read_bytes()
    payload_hash = hashlib.sha256(body).hexdigest()
    now = datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    host = f"{account_id}.r2.cloudflarestorage.com"
    encoded_key = urllib.parse.quote(key, safe="/")
    canonical_uri = f"/{bucket}/{encoded_key}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        ["PUT", canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(signing_key(secret_key, date_stamp), string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    request = urllib.request.Request(
        f"https://{host}{canonical_uri}",
        data=body,
        headers={
            "Authorization": authorization,
            "Content-Type": content_type,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        },
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        response.read()
    return {"path": str(path), "key": key, "url": r2_public_url_for_key(key)}


def media_files_for_folder(folder: Path) -> list[Path]:
    metadata_path = folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    candidates: list[Path] = []
    for value in [metadata.get("image"), metadata.get("sound")]:
        if value:
            path = Path(value)
            local_path = folder / path.name
            if local_path.exists():
                candidates.append(local_path)
            else:
                candidates.append(path)
    for value in metadata.get("images", []) or []:
        path = Path(value)
        local_path = folder / path.name
        if local_path.exists():
            candidates.append(local_path)
        else:
            candidates.append(path)
    for name in ["tiktok-video.mp4", "youtube-video.mp4", "promo-video.mp4"]:
        path = folder / name
        if path.exists():
            candidates.append(path)
    seen: set[str] = set()
    files: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists() and str(resolved) not in seen:
            seen.add(str(resolved))
            files.append(resolved)
    return files


def upload_folder_media_to_r2(folder: str) -> dict[str, Any]:
    target = Path(folder).resolve()
    allowed_roots = [SOCIAL_OUTPUT_DIR.resolve(), TIKTOK_OUTPUT_DIR.resolve(), OUTPUT_DIR.resolve(), CHAPTER_OUTPUT_DIR.resolve()]
    if not any(str(target).startswith(str(root)) for root in allowed_roots):
        raise RuntimeError("Folder is not valid for media upload.")
    uploaded = [upload_file_to_r2(path) for path in media_files_for_folder(target)]
    metadata_path = target / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.setdefault("cloudflare_r2_uploads", []).append(
            {"uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": uploaded}
        )
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"uploaded": uploaded}


def copy_folder_media_to_github(folder: str) -> dict[str, Any]:
    target = Path(folder).resolve()
    allowed_roots = [
        SOCIAL_OUTPUT_DIR.resolve(),
        TIKTOK_OUTPUT_DIR.resolve(),
        OUTPUT_DIR.resolve(),
        YOUTUBE_OUTPUT_DIR.resolve(),
        CHAPTER_OUTPUT_DIR.resolve(),
    ]
    if not any(str(target).startswith(str(root)) for root in allowed_roots):
        raise RuntimeError("Folder is not valid for GitHub media storage.")
    GITHUB_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    for source in media_files_for_folder(target):
        key = media_key_for_generated_file(source)
        destination = GITHUB_MEDIA_DIR / Path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(
            {
                "source": str(source),
                "repo_path": str(destination),
                "key": key,
                "url": github_media_url_for_key(key),
            }
        )
    metadata_path = target / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.setdefault("github_media_copies", []).append(
            {"copied_at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": copied}
        )
        if copied:
            metadata["public_media_urls"] = [item["url"] for item in copied]
            first_image = next((item["url"] for item in copied if Path(item["key"]).suffix.lower() in IMAGE_EXTENSIONS), None)
            if first_image:
                metadata["public_image_url"] = first_image
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"copied": copied, "media_dir": str(GITHUB_MEDIA_DIR), "base_url": github_pages_media_base_url()}


def run_git(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_output(run: subprocess.CompletedProcess[str]) -> str:
    return (run.stdout + "\n" + run.stderr).strip()


def ensure_github_repo() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if not (ROOT / ".git").exists():
        run = run_git(["init", "-b", "main"])
        steps.append({"command": "git init -b main", "returncode": run.returncode, "output": git_output(run)})
        if run.returncode != 0:
            raise RuntimeError(git_output(run) or "Git init failed.")

    branch = run_git(["branch", "--show-current"])
    if branch.returncode == 0 and branch.stdout.strip() != "main":
        run = run_git(["branch", "-M", "main"])
        steps.append({"command": "git branch -M main", "returncode": run.returncode, "output": git_output(run)})

    remote_url = os.environ.get("GITHUB_REMOTE_URL", GITHUB_REMOTE_URL).strip() or GITHUB_REMOTE_URL
    remote = run_git(["remote", "get-url", "origin"])
    if remote.returncode != 0:
        run = run_git(["remote", "add", "origin", remote_url])
        steps.append({"command": "git remote add origin", "returncode": run.returncode, "output": git_output(run)})
    elif remote.stdout.strip() != remote_url:
        run = run_git(["remote", "set-url", "origin", remote_url])
        steps.append({"command": "git remote set-url origin", "returncode": run.returncode, "output": git_output(run)})
    return steps


def publish_folder_media_to_github(folder: str) -> dict[str, Any]:
    if os.environ.get("GITHUB_TOKEN", "").strip():
        return publish_folder_media_to_github_api(folder)
    copied = copy_folder_media_to_github(folder)
    steps = ensure_github_repo()
    paths = ["docs/.nojekyll", "docs/media"]
    add = run_git(["add", *paths])
    steps.append({"command": "git add docs media", "returncode": add.returncode, "output": git_output(add)})
    if add.returncode != 0:
        raise RuntimeError(git_output(add) or "Git could not stage media files.")

    status = run_git(["status", "--porcelain", "--", *paths])
    changed = bool(status.stdout.strip())
    commit_created = False
    if changed:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        commit = run_git(["commit", "-m", f"Publish automation media {timestamp}"])
        steps.append({"command": "git commit media", "returncode": commit.returncode, "output": git_output(commit)})
        if commit.returncode != 0:
            raise RuntimeError(git_output(commit) or "Git could not commit media files.")
        commit_created = True

    push = run_git(["push", "-u", "origin", "main"], timeout=300)
    steps.append({"command": "git push origin main", "returncode": push.returncode, "output": git_output(push)})
    if push.returncode != 0:
        raise RuntimeError(git_output(push) or "Git could not push media files.")

    return {**copied, "published": True, "commitCreated": commit_created, "git": steps}


def auto_publish_generated_media(folder: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if not github_auto_publish_media():
        return payload
    try:
        published = publish_folder_media_to_github(str(folder))
        payload["github_media_publish"] = {
            "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": published.get("copied", []),
            "base_url": published.get("base_url"),
            "commit_created": published.get("commitCreated", False),
        }
        urls = [item["url"] for item in published.get("copied", [])]
        if urls:
            payload["public_media_urls"] = urls
            first_image = next((url for url in urls if Path(urllib.parse.urlparse(url).path).suffix.lower() in IMAGE_EXTENSIONS), None)
            if first_image:
                payload["public_image_url"] = first_image
    except Exception as exc:
        payload.setdefault("automation_warnings", []).append(f"GitHub media publish failed: {exc}")
    metadata_path = folder / "metadata.json"
    if metadata_path.exists():
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def manual_buffer_assist(folder: str, text_kind: str = "instagram") -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    allowed_roots = [SOCIAL_OUTPUT_DIR.resolve(), TIKTOK_OUTPUT_DIR.resolve(), OUTPUT_DIR.resolve(), YOUTUBE_OUTPUT_DIR.resolve()]
    if not any(str(post_folder).startswith(str(root)) for root in allowed_roots):
        raise RuntimeError("Folder is not valid for Buffer assist.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if str(post_folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
        text = metadata.get("caption", "")
        text_file = post_folder / "caption.txt"
    elif str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        text = metadata.get("instagram" if text_kind == "instagram" else "x", "")
        text_file = post_folder / ("instagram.txt" if text_kind == "instagram" else "x.txt")
    elif str(post_folder).startswith(str(YOUTUBE_OUTPUT_DIR.resolve())):
        text = metadata.get("description", "")
        text_file = post_folder / "youtube-description.txt"
    else:
        text = metadata.get("caption") or metadata.get("patreon_note") or metadata.get("royal_road_note") or ""
        text_file = post_folder / "caption.txt"
        if not text_file.exists():
            text_file.write_text(text + "\n", encoding="utf-8")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Content -Raw -LiteralPath '{text_file}' | Set-Clipboard"], check=False)
    except Exception:
        pass
    try:
        os.startfile(str(post_folder))
    except Exception:
        pass
    try:
        os.startfile("https://publish.buffer.com/calendar")
    except Exception:
        pass
    metadata.setdefault("manual_buffer_assists", []).append(
        {
            "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text_kind": text_kind,
            "text_file": str(text_file),
            "folder": str(post_folder),
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "message": "Opened Buffer and the media folder. Caption copied to clipboard.",
        "folder": str(post_folder),
        "text_file": str(text_file),
        "text": text,
    }


def mark_buffer_queued(folder: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    allowed_roots = [SOCIAL_OUTPUT_DIR.resolve(), TIKTOK_OUTPUT_DIR.resolve(), OUTPUT_DIR.resolve(), YOUTUBE_OUTPUT_DIR.resolve()]
    if not any(str(post_folder).startswith(str(root)) for root in allowed_roots):
        raise RuntimeError("Folder is not valid for Buffer status.")
    metadata_path = post_folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    metadata["manual_buffer_queued"] = {
        "queued_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "confirmed_by_user",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (post_folder / "manual-buffer-queued.txt").write_text(
        f"Buffer post manually marked queued at {metadata['manual_buffer_queued']['queued_at']}\n",
        encoding="utf-8",
    )
    return {"queued": True, "folder": str(post_folder)}


def buffer_asset_for_file(path: Path) -> dict[str, Any] | None:
    url = public_url_for_generated_file(path)
    if not url:
        return None
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        return {"video": {"url": url}}
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return {"image": {"url": url}}
    return None


def create_buffer_post(channel_id: str, text: str, media_paths: list[str], mode: str = "addToQueue") -> dict[str, Any]:
    assets = []
    for media_path in media_paths:
        asset = buffer_asset_for_file(Path(media_path))
        if asset:
            assets.append(asset)
    if media_paths and not assets:
        raise RuntimeError("Buffer needs public HTTPS media URLs. Set BUFFER_PUBLIC_BASE_URL to where generated media is hosted.")
    result = buffer_graphql(
        """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post { id text dueAt channelId assets { id mimeType } }
            }
            ... on MutationError { message }
          }
        }
        """,
        {
            "input": {
                "text": text,
                "channelId": channel_id,
                "schedulingType": "automatic",
                "mode": mode,
                "assets": assets,
            }
        },
    )
    response = result.get("data", {}).get("createPost", {})
    if response.get("message"):
        raise RuntimeError(response["message"])
    return response


def buffer_post_from_folder(folder: str, channel_ids: list[str], text_kind: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    if r2_configured():
        upload_folder_media_to_r2(str(post_folder))
    elif github_auto_publish_media():
        publish_folder_media_to_github(str(post_folder))
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        text = metadata.get("instagram" if text_kind == "instagram" else "x", "")
        media = [metadata.get("image", "")]
    elif str(post_folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
        text = metadata.get("caption", "")
        video = post_folder / "tiktok-video.mp4"
        media = [str(video)] if video.exists() else metadata.get("images", [])
    else:
        text = metadata.get("caption") or metadata.get("patreon_note") or metadata.get("royal_road_note") or ""
        media = metadata.get("images", [])
    posts = []
    for channel_id in channel_ids:
        posts.append(create_buffer_post(channel_id, text, [m for m in media if m]))
    metadata.setdefault("buffer_posts", []).append({"posted_at": time.strftime("%Y-%m-%d %H:%M:%S"), "responses": posts})
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"posts": posts}


def multipart_bearer_request(url: str, token: str, fields: dict[str, str], files: dict[str, Path]) -> dict[str, Any]:
    boundary = f"----AutomationTool{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, path in files.items():
        filename = path.name
        content_type = "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_instagram_accounts() -> dict[str, Any]:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Save an access token first.")
    return graph_get(
        "me/accounts",
        {
            "fields": "id,name,instagram_business_account{id,username,name}",
            "access_token": token,
        },
    )


def public_social_image_url(folder: Path, image: Path) -> str | None:
    base = normalize_public_base_url(os.environ.get("INSTAGRAM_PUBLIC_BASE_URL", ""))
    if not base:
        return None
    relative = image.relative_to(SOCIAL_OUTPUT_DIR).as_posix()
    return f"{base}/{urllib.parse.quote(relative, safe='/')}"


def publish_instagram_image(folder: str) -> dict[str, Any]:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    ig_user_id = os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()
    if not token or not ig_user_id:
        raise RuntimeError("Instagram is not configured. Add INSTAGRAM_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN to .env.local.")

    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        raise RuntimeError("Social post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    image_path = Path(metadata["image"]).resolve()
    image_url = metadata.get("public_image_url") or public_social_image_url(post_folder, image_path)
    if not image_url:
        raise RuntimeError(
            "Instagram needs a public HTTPS image URL. Set INSTAGRAM_PUBLIC_BASE_URL in .env.local "
            "to the public URL where social-posts is hosted."
        )
    if not image_url.lower().startswith("https://"):
        raise RuntimeError("INSTAGRAM_PUBLIC_BASE_URL must start with https:// for Instagram publishing.")

    graph = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}"
    container = form_request(
        f"{graph}/{ig_user_id}/media",
        {
            "image_url": image_url,
            "caption": metadata.get("instagram", ""),
            "alt_text": metadata.get("alt_text", ""),
            "access_token": token,
        },
    )
    creation_id = container.get("id")
    if not creation_id:
        raise RuntimeError(f"Instagram did not return a media container id: {container}")
    published = form_request(
        f"{graph}/{ig_user_id}/media_publish",
        {"creation_id": creation_id, "access_token": token},
    )
    metadata["instagram_publish"] = {
        "container_id": creation_id,
        "publish_response": published,
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "image_url": image_url,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"container_id": creation_id, "publish_response": published, "image_url": image_url}


def manual_instagram_assist(folder: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        raise RuntimeError("Social post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    caption = metadata.get("instagram", "")
    image_path = Path(metadata["image"]).resolve()
    caption_file = post_folder / "instagram.txt"

    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Content -Raw -LiteralPath '{caption_file}' | Set-Clipboard"], check=False)
    except Exception:
        pass
    try:
        os.startfile(str(post_folder))
    except Exception:
        pass
    try:
        os.startfile("https://www.instagram.com/")
    except Exception:
        pass

    metadata["manual_instagram_assist"] = {
        "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "image": str(image_path),
        "caption_file": str(caption_file),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "image": str(image_path),
        "caption": caption,
        "caption_file": str(caption_file),
        "folder": str(post_folder),
        "message": "Opened Instagram and the post folder. Caption copied to clipboard.",
    }


def mark_manual_instagram_posted(folder: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        raise RuntimeError("Social post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["manual_instagram_posted"] = {
        "posted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "confirmed_by_user",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (post_folder / "manual-posted.txt").write_text(
        f"Instagram post manually marked complete at {metadata['manual_instagram_posted']['posted_at']}\n",
        encoding="utf-8",
    )
    return {"posted": True, "folder": str(post_folder)}


def manual_x_assist(folder: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        raise RuntimeError("Social post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    image_path = Path(metadata["image"]).resolve()
    x_file = post_folder / "x.txt"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Content -Raw -LiteralPath '{x_file}' | Set-Clipboard"], check=False)
    except Exception:
        pass
    try:
        os.startfile(str(post_folder))
    except Exception:
        pass
    try:
        os.startfile("https://x.com/compose/post")
    except Exception:
        pass
    metadata["manual_x_assist"] = {
        "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "image": str(image_path),
        "x_file": str(x_file),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "image": str(image_path),
        "text": metadata.get("x", ""),
        "x_file": str(x_file),
        "folder": str(post_folder),
        "message": "Opened X and the post folder. X text copied to clipboard.",
    }


def mark_manual_x_posted(folder: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        raise RuntimeError("Social post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["manual_x_posted"] = {
        "posted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "confirmed_by_user",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (post_folder / "manual-x-posted.txt").write_text(
        f"X post manually marked complete at {metadata['manual_x_posted']['posted_at']}\n",
        encoding="utf-8",
    )
    return {"posted": True, "folder": str(post_folder)}


def publish_x_post(folder: str) -> dict[str, Any]:
    token = os.environ.get("X_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("X is not configured. Add X_ACCESS_TOKEN to .env.local or save it in Connections.")
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        raise RuntimeError("Social post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    image_path = Path(metadata["image"]).resolve()

    upload = multipart_bearer_request(
        "https://api.x.com/2/media/upload",
        token,
        {"media_category": "tweet_image"},
        {"media": image_path},
    )
    media_id = upload.get("data", {}).get("id") or upload.get("media_id_string") or upload.get("media_id")
    if not media_id:
        raise RuntimeError(f"X media upload did not return a media id: {upload}")
    created = bearer_json_request(
        "https://api.x.com/2/tweets",
        token,
        {"text": metadata.get("x", ""), "media": {"media_ids": [str(media_id)]}},
    )
    metadata["x_publish"] = {
        "media_upload": upload,
        "post_response": created,
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"media_id": media_id, "post_response": created}


def manual_tiktok_assist(folder: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
        raise RuntimeError("TikTok post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain TikTok metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    caption_file = post_folder / "caption.txt"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Content -Raw -LiteralPath '{caption_file}' | Set-Clipboard"], check=False)
    except Exception:
        pass
    try:
        os.startfile(str(post_folder))
    except Exception:
        pass
    try:
        os.startfile("https://www.tiktok.com/upload")
    except Exception:
        pass
    metadata["manual_tiktok_assist"] = {
        "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "caption_file": str(caption_file),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "folder": str(post_folder),
        "images": metadata.get("images", []),
        "sound": metadata.get("sound", ""),
        "caption": metadata.get("caption", ""),
        "message": "Opened TikTok upload and the post folder. Caption copied to clipboard.",
    }


def mark_manual_tiktok_posted(folder: str) -> dict[str, Any]:
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
        raise RuntimeError("TikTok post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain TikTok metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["manual_tiktok_posted"] = {
        "posted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "confirmed_by_user",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (post_folder / "manual-tiktok-posted.txt").write_text(
        f"TikTok post manually marked complete at {metadata['manual_tiktok_posted']['posted_at']}\n",
        encoding="utf-8",
    )
    return {"posted": True, "folder": str(post_folder)}


def manual_text_platform_assist(folder: str, platform: str) -> dict[str, Any]:
    campaign_folder = Path(folder).resolve()
    if not str(campaign_folder).startswith(str(OUTPUT_DIR.resolve())):
        raise RuntimeError("Campaign folder is not valid.")
    file_map = {
        "patreon": ("patreon-note.txt", "https://www.patreon.com/posts/new", "Patreon"),
        "royal-road": ("royal-road-note.txt", "https://www.royalroad.com/author-dashboard", "Royal Road"),
    }
    if platform not in file_map:
        raise RuntimeError("Unknown platform.")
    filename, url, label = file_map[platform]
    text_file = campaign_folder / filename
    if not text_file.exists():
        raise RuntimeError(f"{filename} was not found in this campaign.")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-Content -Raw -LiteralPath '{text_file}' | Set-Clipboard"], check=False)
    except Exception:
        pass
    try:
        os.startfile(str(campaign_folder))
    except Exception:
        pass
    try:
        os.startfile(url)
    except Exception:
        pass
    metadata_path = campaign_folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    metadata[f"manual_{platform}_assist"] = {
        "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "text_file": str(text_file),
        "url": url,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "platform": label,
        "folder": str(campaign_folder),
        "text_file": str(text_file),
        "message": f"Opened {label} and the campaign folder. Prepared text copied to clipboard.",
    }


def mark_manual_text_platform_posted(folder: str, platform: str) -> dict[str, Any]:
    campaign_folder = Path(folder).resolve()
    if not str(campaign_folder).startswith(str(OUTPUT_DIR.resolve())):
        raise RuntimeError("Campaign folder is not valid.")
    labels = {"patreon": "Patreon", "royal-road": "Royal Road"}
    if platform not in labels:
        raise RuntimeError("Unknown platform.")
    metadata_path = campaign_folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    key = f"manual_{platform}_posted"
    metadata[key] = {
        "posted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "confirmed_by_user",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (campaign_folder / f"manual-{platform}-posted.txt").write_text(
        f"{labels[platform]} manually marked complete at {metadata[key]['posted_at']}\n",
        encoding="utf-8",
    )
    return {"posted": True, "platform": labels[platform], "folder": str(campaign_folder)}


def analyze_with_openai(title: str, chapter: str) -> dict[str, Any]:
    prompt = f"""
    Create promotional material for this web novel chapter.

    Return strict JSON with:
    - phrases: exactly 3 short dramatic excerpt-style phrases, 8 to 18 words each
    - image_prompts: exactly 3 vertical TikTok/Instagram image prompts, cinematic but not text-heavy
    - caption: one compact social caption with hashtags
    - royal_road_note: a short Royal Road update note
    - patreon_note: a short Patreon teaser note

    Chapter title: {title}

    Chapter text:
    {chapter[:12000]}
    """
    result = openai_request(
        "chat/completions",
        {
            "model": os.environ.get("OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
            "messages": [
                {"role": "system", "content": "You are a sharp web-novel marketing assistant. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        },
    )
    content = result["choices"][0]["message"]["content"]
    return json.loads(content)


def write_chapter_with_openai(
    novel: str,
    chapter_number: str,
    chapter_title: str,
    outline: str,
    continuity: str,
    target_words: int,
) -> dict[str, Any]:
    prompt = f"""
    Write the next chapter for the web novel {novel}.

    Chapter number: {chapter_number}
    Chapter title: {chapter_title or 'Create a fitting title'}
    Target length: about {target_words} words

    Outline:
    {outline}

    Continuity and style notes:
    {continuity}

    Requirements:
    - Preserve continuity and character motivations from the notes.
    - Write polished prose, not an outline.
    - Include a chapter title.
    - End with forward momentum.
    - Do not include marketing copy.

    Return strict JSON with:
    - title
    - chapter_text
    - short_summary
    - continuity_notes
    """
    result = openai_request(
        "chat/completions",
        {
            "model": os.environ.get("OPENAI_CHAPTER_MODEL", os.environ.get("OPENAI_TEXT_MODEL", "gpt-4.1")),
            "messages": [
                {"role": "system", "content": "You are a careful serial web-novel ghostwriter. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.85,
            "response_format": {"type": "json_object"},
        },
    )
    data = json.loads(result["choices"][0]["message"]["content"])
    title = data.get("title") or chapter_title or f"Chapter {chapter_number}"
    chapter_text = data.get("chapter_text") or ""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    folder = CHAPTER_OUTPUT_DIR / f"{timestamp}-{slugify(novel)}-chapter-{slugify(str(chapter_number))}"
    folder.mkdir(parents=True, exist_ok=True)
    chapter_file = folder / "chapter.txt"
    chapter_file.write_text(f"{title}\n\n{chapter_text.strip()}\n", encoding="utf-8")
    (folder / "summary.txt").write_text(str(data.get("short_summary", "")).strip() + "\n", encoding="utf-8")
    (folder / "continuity-notes.txt").write_text(str(data.get("continuity_notes", "")).strip() + "\n", encoding="utf-8")

    campaign = make_campaign(title, chapter_text, True)
    data.update(
        {
            "title": title,
            "chapter_text": chapter_text,
            "folder": str(folder),
            "chapter_file": str(chapter_file),
            "campaign": campaign,
        }
    )
    (folder / "metadata.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def youtube_metadata_from_text(chapter_title: str, chapter_text: str) -> dict[str, str]:
    fallback_title = chapter_title.strip() or "New Web Novel Chapter"
    if os.environ.get("OPENAI_API_KEY"):
        try:
            result = openai_request(
                "chat/completions",
                {
                    "model": os.environ.get("OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
                    "messages": [
                        {"role": "system", "content": "Create YouTube metadata for web-novel chapter videos. Return only JSON."},
                        {
                            "role": "user",
                            "content": (
                                "Return JSON with title, description, and tags array. "
                                "Keep title under 90 characters. Description should mention this is a web novel chapter narration.\n\n"
                                f"Chapter title: {fallback_title}\n\nChapter text:\n{chapter_text[:8000]}"
                            ),
                        },
                    ],
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                },
            )
            data = json.loads(result["choices"][0]["message"]["content"])
            return {
                "title": str(data.get("title") or fallback_title),
                "description": str(data.get("description") or f"Listen to {fallback_title}, a web novel chapter narration."),
                "tags": ", ".join(data.get("tags", []) if isinstance(data.get("tags"), list) else []),
            }
        except Exception:
            pass
    description = (
        f"Listen to {fallback_title}, a web novel chapter narration.\n\n"
        "Follow for more chapters, story updates, and serial fiction releases."
    )
    return {"title": fallback_title[:90], "description": description, "tags": "web novel, audiobook, serial fiction"}


def build_youtube_from_text(chapter_title: str, chapter_text: str) -> dict[str, Any]:
    if not chapter_text.strip():
        raise RuntimeError("Chapter text is required.")
    metadata = youtube_metadata_from_text(chapter_title, chapter_text)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    folder = YOUTUBE_OUTPUT_DIR / f"{timestamp}-{slugify(metadata['title'])}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "chapter-text.txt").write_text(chapter_text.strip() + "\n", encoding="utf-8")
    (folder / "youtube-title.txt").write_text(metadata["title"].strip() + "\n", encoding="utf-8")
    (folder / "youtube-description.txt").write_text(metadata["description"].strip() + "\n", encoding="utf-8")
    (folder / "youtube-tags.txt").write_text(metadata["tags"].strip() + "\n", encoding="utf-8")
    backgrounds = choose_background_videos(3)
    write_youtube_text_video_script(folder, metadata["title"], chapter_text, backgrounds)
    result = {
        **metadata,
        "folder": str(folder),
        "background_videos": [str(path) for path in backgrounds],
        "script": str(folder / "build_youtube_video.py"),
    }
    (folder / "metadata.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return auto_publish_generated_media(folder, result)


def write_youtube_text_video_script(folder: Path, title: str, chapter_text: str, background_videos: list[Path]) -> None:
    ffmpeg_exe = find_ffmpeg_executable()
    narration_text = re.sub(r"\s+", " ", chapter_text).strip()
    script = folder / "build_youtube_video.py"
    selected = [str(path) for path in background_videos]
    script.write_text(
        f'''from pathlib import Path
import subprocess

folder = Path(__file__).resolve().parent
background_videos = {selected!r}
title = {title!r}
narration_text = {narration_text!r}
ffmpeg_exe = {ffmpeg_exe!r}
audio = folder / "youtube-voiceover.wav"
output = folder / "youtube-video.mp4"

if not background_videos:
    raise SystemExit("No background videos found.")

print("Creating narration...")
powershell = f"""
Add-Type -AssemblyName System.Speech;
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;
$speak.Rate = -1;
$speak.SetOutputToWaveFile('{{audio}}');
$speak.Speak(@'
{{narration_text}}
'@);
$speak.Dispose();
"""
subprocess.run(["powershell", "-NoProfile", "-Command", powershell], check=False)

clips = []
for index, video in enumerate(background_videos, start=1):
    clip = folder / f"youtube-bg-{{index}}.mp4"
    subprocess.run([
        ffmpeg_exe, "-y", "-stream_loop", "-1", "-i", video,
        "-t", "30", "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
        "-an", "-pix_fmt", "yuv420p", str(clip)
    ], check=False)
    if clip.exists():
        clips.append(clip)

if not clips:
    raise SystemExit("No clips were created.")

concat = folder / "youtube-clips.txt"
concat.write_text("\\n".join([f"file '{{clip}}'" for clip in clips]) + "\\n", encoding="utf-8")

command = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-stream_loop", "-1", "-i", str(concat)]
if audio.exists():
    command += ["-i", str(audio), "-shortest"]
command += ["-vf", "drawbox=x=0:y=850:w=1920:h=150:color=black@0.45:t=fill,drawtext=text='" + title.replace("\\\\", "\\\\\\\\").replace(":", "\\\\:").replace("'", "\\\\'") + "':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=905", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)]
subprocess.run(command, check=False)
print(f"YouTube video target: {{output}}")
''',
        encoding="utf-8",
    )


def make_fallback_image_prompt(title: str, phrase: str) -> str:
    words = re.findall(r"[a-zA-Z]{4,}", f"{title} {phrase}".lower())
    query = " ".join(words[:5]) or "fantasy novel dramatic scene"
    return query


def download_url(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "AutomationTool/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())


def create_openai_image(prompt: str, target: Path) -> None:
    result = openai_request(
        "images/generations",
        {
            "model": os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            "prompt": prompt,
            "size": "1024x1536",
            "quality": "medium",
            "n": 1,
        },
    )
    image = result["data"][0]
    if image.get("b64_json"):
        target.write_bytes(base64.b64decode(image["b64_json"]))
        return
    if image.get("url"):
        download_url(image["url"], target)
        return
    raise RuntimeError("Image response did not include image data.")


def create_fallback_image(query: str, target: Path, index: int) -> None:
    seed = urllib.parse.quote_plus(f"{query}-{index}")
    url = f"https://picsum.photos/seed/{seed}/1024/1536"
    download_url(url, target)


def write_text_artifacts(folder: Path, payload: dict[str, Any]) -> None:
    (folder / "phrases.txt").write_text("\n".join(payload["phrases"]) + "\n", encoding="utf-8")
    (folder / "caption.txt").write_text(payload["caption"].strip() + "\n", encoding="utf-8")
    (folder / "royal-road-note.txt").write_text(payload["royal_road_note"].strip() + "\n", encoding="utf-8")
    (folder / "patreon-note.txt").write_text(payload["patreon_note"].strip() + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def find_background_videos(limit: int | None = None) -> list[Path]:
    if not BACKGROUND_VIDEO_DIR.exists():
        return []
    preferred: list[Path] = []
    fallback: list[Path] = []
    for path in BACKGROUND_VIDEO_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            if path.stem.lower().startswith("bg_") or path.stem.lower().startswith("background"):
                preferred.append(path)
            else:
                fallback.append(path)
            if limit and len(preferred) >= limit:
                break
    videos = preferred or fallback
    return videos[:limit] if limit else videos


def choose_background_videos(count: int = 3) -> list[Path]:
    videos = find_background_videos()
    if len(videos) <= count:
        return videos
    return random.sample(videos, count)


def make_campaign(title: str, chapter: str, use_openai: bool) -> dict[str, Any]:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    folder = OUTPUT_DIR / f"{timestamp}-{slugify(title)}"
    folder.mkdir(parents=True, exist_ok=True)

    source = "fallback"
    try:
        if use_openai:
            material = analyze_with_openai(title, chapter)
            source = "openai"
        else:
            raise RuntimeError("OpenAI disabled for this run.")
    except Exception as exc:
        phrases = fallback_phrases(chapter)
        material = {
            "phrases": phrases,
            "image_prompts": [make_fallback_image_prompt(title, phrase) for phrase in phrases],
            "caption": fallback_caption(title, phrases),
            "royal_road_note": f"{title or 'The new chapter'} is now available. Thank you for reading.",
            "patreon_note": f"Early access readers can jump into {title or 'the new chapter'} now.",
            "warning": str(exc),
        }

    material["title"] = title
    material["source"] = source
    material["folder"] = str(folder)
    write_text_artifacts(folder, material)

    images: list[str] = []
    for index, prompt in enumerate(material["image_prompts"][:3], start=1):
        target = folder / f"promo-{index}.png"
        try:
            if source == "openai":
                create_openai_image(prompt, target)
            else:
                create_fallback_image(prompt, target, index)
        except Exception as exc:
            placeholder = ASSET_DIR / "placeholder.svg"
            target = folder / f"promo-{index}.svg"
            text = placeholder.read_text(encoding="utf-8").replace("{{PHRASE}}", material["phrases"][index - 1])
            target.write_text(text, encoding="utf-8")
            material.setdefault("image_warnings", []).append(str(exc))
        images.append(str(target))

    material["images"] = images
    background_videos = choose_background_videos(3)
    material["background_videos"] = [str(path) for path in background_videos]
    write_video_helper(folder, title, material["phrases"], images)
    write_youtube_video_helper(folder, title, material["phrases"], background_videos)
    write_text_artifacts(folder, material)
    return auto_publish_generated_media(folder, material)


def write_video_helper(folder: Path, title: str, phrases: list[str], images: list[str]) -> None:
    script = folder / "make_video.py"
    text = "\n".join(phrases)
    ffmpeg_exe = find_ffmpeg_executable()
    script.write_text(
        f'''from pathlib import Path
import subprocess

folder = Path(__file__).resolve().parent
images = {[Path(image).name for image in images]!r}
voice_text = {text!r}
ffmpeg_exe = {ffmpeg_exe!r}

audio = folder / "voiceover.wav"
video = folder / "promo-video.mp4"

print("Creating voiceover with Windows speech if available...")
powershell = f"""
Add-Type -AssemblyName System.Speech;
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;
$speak.Rate = -1;
$speak.SetOutputToWaveFile('{{audio}}');
$speak.Speak(@'
{{voice_text}}
'@);
$speak.Dispose();
"""
subprocess.run(["powershell", "-NoProfile", "-Command", powershell], check=False)

print("Creating a simple vertical video with ffmpeg if available...")
concat = folder / "slides.txt"
concat.write_text("\\n".join([f"file '{{folder / image}}'\\nduration 3" for image in images] + [f"file '{{folder / images[-1]}}'"]) + "\\n")
subprocess.run([
    ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
    "-i", str(audio), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
    "-shortest", "-pix_fmt", "yuv420p", str(video)
], check=False)

osp = folder / "openshot-notes.txt"
osp.write_text("Import the three promo images and voiceover.wav into OpenShot. Set the project to vertical 1080x1920, place each image for about 3 seconds, then export as MP4.\\n")
print(f"Done. Output folder: {{folder}}")
''',
        encoding="utf-8",
    )
    (folder / "video-text.txt").write_text(f"{title}\n\n{text}\n", encoding="utf-8")


def escape_drawtext(value: str) -> str:
    value = value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return value.replace("\n", "\\n")


def write_youtube_video_helper(folder: Path, title: str, phrases: list[str], background_videos: list[Path]) -> None:
    script = folder / "make_youtube_video.py"
    selected = [str(path) for path in background_videos]
    voice_text = f"{title}. " + " ".join(phrases)
    ffmpeg_exe = find_ffmpeg_executable()
    script.write_text(
        f'''from pathlib import Path
import subprocess

folder = Path(__file__).resolve().parent
background_videos = {selected!r}
phrases = {phrases!r}
voice_text = {voice_text!r}
ffmpeg_exe = {ffmpeg_exe!r}

audio = folder / "youtube-voiceover.wav"
output = folder / "youtube-video.mp4"

if len(background_videos) < 1:
    raise SystemExit("No background videos were found. Check BACKGROUND_VIDEO_DIR in .env.local or app.py.")

print("Creating narration with Windows speech...")
powershell = f"""
Add-Type -AssemblyName System.Speech;
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;
$speak.Rate = -1;
$speak.SetOutputToWaveFile('{{audio}}');
$speak.Speak(@'
{{voice_text}}
'@);
$speak.Dispose();
"""
subprocess.run(["powershell", "-NoProfile", "-Command", powershell], check=False)

clips = []
for index, video in enumerate(background_videos[:3], start=1):
    clip = folder / f"youtube-bg-{{index}}.mp4"
    phrase = phrases[index - 1] if index - 1 < len(phrases) else phrases[-1]
    draw = (
        "scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,"
        "drawbox=x=0:y=760:w=1920:h=220:color=black@0.52:t=fill,"
        "drawtext=text='" + {escape_drawtext.__name__}(phrase) + "':"
        "fontcolor=white:fontsize=54:line_spacing=10:"
        "box=0:x=(w-text_w)/2:y=830"
    )
    subprocess.run([
        ffmpeg_exe, "-y", "-stream_loop", "-1", "-i", video,
        "-t", "8", "-vf", draw, "-an", "-pix_fmt", "yuv420p", str(clip)
    ], check=False)
    if clip.exists():
        clips.append(clip)

if not clips:
    raise SystemExit("ffmpeg did not create any clips. Install ffmpeg or use OpenShot with youtube-project-notes.txt.")

concat = folder / "youtube-clips.txt"
concat.write_text("\\n".join([f"file '{{clip}}'" for clip in clips]) + "\\n", encoding="utf-8")

command = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat)]
if audio.exists():
    command += ["-i", str(audio), "-shortest"]
command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)]
subprocess.run(command, check=False)

print(f"YouTube video target: {{output}}")
'''.replace(f"{escape_drawtext.__name__}(phrase)", "phrase.replace('\\\\', '\\\\\\\\').replace(':', '\\\\:').replace(\"'\", \"\\\\'\").replace('\\n', '\\\\n')"),
        encoding="utf-8",
    )

    notes = [
        "YouTube video build notes",
        "",
        "Selected background videos:",
        *[f"- {path}" for path in selected],
        "",
        "Run make_youtube_video.py to create youtube-video.mp4 with ffmpeg.",
        "If using OpenShot instead, import the three selected background videos and youtube-voiceover.wav, then place the phrases as text overlays.",
        "Recommended export: 1920x1080 MP4 for standard YouTube. For Shorts, switch the OpenShot project to 1080x1920.",
    ]
    (folder / "youtube-project-notes.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")


def find_examples() -> list[dict[str, str]]:
    roots = [ROOT.parent, ROOT]
    patterns = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".txt", ".md"}
    found: list[dict[str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if len(found) >= 80:
                return found
            if path.is_file() and path.suffix.lower() in patterns:
                if any(part.lower() in {"node_modules", ".git", "__pycache__", "campaigns"} for part in path.parts):
                    continue
                found.append({"name": path.name, "path": str(path)})
    return found


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chapter Promo Builder</title>
  <style>
    :root { color-scheme: light; --ink:#172026; --muted:#5b6770; --line:#d9e1e7; --panel:#f7f9fb; --accent:#0f766e; --accent2:#b45309; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, Helvetica, sans-serif; color: var(--ink); background: #ffffff; }
    header { padding: 20px 28px; border-bottom: 1px solid var(--line); display:flex; align-items:center; justify-content:space-between; gap:16px; }
    h1 { margin:0; font-size: clamp(22px, 3vw, 34px); letter-spacing: 0; }
    main { display:grid; grid-template-columns: minmax(320px, 520px) 1fr; min-height: calc(100vh - 77px); }
    form { padding: 24px 28px; border-right: 1px solid var(--line); background: var(--panel); }
    label { display:block; font-weight:700; margin: 16px 0 8px; }
    input, textarea { width:100%; border:1px solid var(--line); border-radius:6px; padding:12px; font: inherit; background:#fff; color:var(--ink); }
    select { border:1px solid var(--line); border-radius:6px; padding:10px; font: inherit; background:#fff; color:var(--ink); min-width:160px; }
    textarea { min-height: 48vh; resize: vertical; line-height: 1.45; }
    textarea.short { min-height: 190px; }
    .row { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:16px; }
    .toggle { display:flex; align-items:center; gap:8px; color:var(--muted); font-weight:600; }
    .inline { margin:0; }
    hr { border:0; border-top:1px solid var(--line); margin:26px 0; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    details { border:1px solid var(--line); border-radius:8px; background:#fff; padding:12px; }
    summary { cursor:pointer; font-weight:700; }
    details[open] summary { margin-bottom:12px; }
    button { border:0; border-radius:6px; padding: 12px 16px; font-weight:700; cursor:pointer; background:var(--accent); color:#fff; }
    button.secondary { background:#24313a; }
    button:disabled { opacity:.55; cursor: wait; }
    section { padding:24px 28px; }
    .status { color:var(--muted); margin-bottom:18px; }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap:16px; }
    .card { border:1px solid var(--line); border-radius:8px; overflow:hidden; background:#fff; }
    .card img { width:100%; aspect-ratio: 9 / 13.5; object-fit:cover; display:block; background:#eef2f5; }
    .card p { margin:0; padding:12px; font-weight:700; line-height:1.3; }
    .copy { border:1px solid var(--line); border-radius:8px; padding:14px; margin-top:16px; white-space:pre-wrap; line-height:1.45; background:#fff; }
    .meta { margin-top:12px; color:var(--muted); font-size:14px; overflow-wrap:anywhere; }
    .examples { margin-top:28px; }
    .examples ul { padding-left:18px; color:var(--muted); }
    @media (max-width: 860px) { main { grid-template-columns: 1fr; } form { border-right:0; border-bottom:1px solid var(--line); } }
  </style>
</head>
<body>
  <header>
    <h1>Chapter Promo Builder</h1>
    <button class="secondary" id="scanBtn" type="button">Scan Examples</button>
  </header>
  <main>
    <form id="promoForm">
      <h2>Write New Chapter</h2>
      <label for="writeNovel">Novel</label>
      <select id="writeNovel"></select>
      <label for="writeChapterNumber">Chapter number</label>
      <input id="writeChapterNumber" placeholder="42">
      <label for="writeChapterTitle">Chapter title</label>
      <input id="writeChapterTitle" placeholder="Optional">
      <label for="writeOutline">Outline</label>
      <textarea id="writeOutline" class="short" placeholder="What should happen in this chapter?"></textarea>
      <label for="writeContinuity">Continuity and style notes</label>
      <textarea id="writeContinuity" class="short" placeholder="Recent events, character state, tone, POV, must-include details..."></textarea>
      <label for="writeTargetWords">Target words</label>
      <input id="writeTargetWords" type="number" min="500" max="10000" step="250" value="3000">
      <div class="row">
        <button id="writeChapterBtn" type="button">Write Chapter + Build Promo</button>
      </div>
      <hr>
      <h2>Chapter Promo</h2>
      <label for="title">Chapter title</label>
      <input id="title" name="title" placeholder="Chapter 42: The Door Under the City">
      <label for="chapter">Chapter text</label>
      <textarea id="chapter" name="chapter" placeholder="Paste the chapter here..."></textarea>
      <div class="row">
        <button id="buildBtn" type="submit">Build Promo Pack</button>
        <label class="toggle"><input id="useOpenAI" type="checkbox" checked> Use ChatGPT/images when configured</label>
      </div>
      <hr>
      <h2>Daily Social Post</h2>
      <div class="row">
        <label class="inline" for="socialNovel">Novel</label>
        <select id="socialNovel"></select>
        <label class="inline" for="socialDay">Day</label>
        <select id="socialDay"></select>
      </div>
      <label for="socialPrompt">Reusable prompt</label>
      <textarea id="socialPrompt" class="short" placeholder="Prompt template"></textarea>
      <div class="row">
        <button id="socialBtn" type="button">Create Instagram/X Post</button>
      </div>
      <hr>
      <h2>TikTok Post</h2>
      <div class="row">
        <label class="inline" for="tiktokNovel">Novel</label>
        <select id="tiktokNovel"></select>
        <label class="inline" for="tiktokChapter">Chapter</label>
        <select id="tiktokChapter"></select>
      </div>
      <label for="tiktokManualChapter">Chapter to create if missing</label>
      <input id="tiktokManualChapter" placeholder="Example: 36">
      <label for="tiktokVisualPrompt">TikTok image prompt</label>
      <textarea id="tiktokVisualPrompt" class="short" placeholder="Describe the scene, mood, characters, or chapter hook for missing images."></textarea>
      <div class="row">
        <button id="tiktokBtn" type="button">Create TikTok Pack</button>
      </div>
      <hr>
      <h2>YouTube Video</h2>
      <label for="youtubeTitle">Chapter/video title</label>
      <input id="youtubeTitle" placeholder="Optional title">
      <label for="youtubeText">Text to narrate</label>
      <textarea id="youtubeText" class="short" placeholder="Paste chapter text for the YouTube narration..."></textarea>
      <div class="row">
        <button id="youtubeTextBtn" type="button">Create YouTube Video Files</button>
      </div>
      <hr>
      <h2>Posting Schedule</h2>
      <div class="row">
        <button id="scheduleBtn" type="button">Show Schedule</button>
        <button id="todayBtn" class="secondary" type="button">Show Today</button>
      </div>
      <hr>
      <details id="connectionPanel">
        <summary>Connections</summary>
        <label for="openaiApiKey">OpenAI API key</label>
        <input id="openaiApiKey" type="password" placeholder="Paste OpenAI API key here">
        <label for="instagramAccountId">Instagram account ID</label>
        <input id="instagramAccountId" placeholder="1784...">
        <label for="instagramAccessToken">Instagram/Facebook access token</label>
        <input id="instagramAccessToken" type="password" placeholder="Paste token here, not in chat">
        <label for="instagramPublicBaseUrl">Public image base URL</label>
        <input id="instagramPublicBaseUrl" placeholder="https://your-public-host/social-posts">
        <label for="xAccessToken">X access token</label>
        <input id="xAccessToken" type="password" placeholder="Paste X user access token here">
        <label for="bufferApiKey">Buffer API key</label>
        <input id="bufferApiKey" type="password" placeholder="Paste Buffer API key here">
        <label for="bufferPublicBaseUrl">Buffer public media base URL</label>
        <input id="bufferPublicBaseUrl" placeholder="https://your-public-host/social-posts">
        <label for="bufferChannelIds">Buffer channel IDs</label>
        <input id="bufferChannelIds" placeholder="Comma-separated channel IDs for Instagram, TikTok, YouTube">
        <label for="githubPagesMediaBaseUrl">GitHub Pages media base URL</label>
        <input id="githubPagesMediaBaseUrl" placeholder="https://azureinkblade-ops.github.io/Automation-tool/media">
        <label for="githubRemoteUrl">GitHub repository URL</label>
        <input id="githubRemoteUrl" placeholder="https://github.com/azureinkblade-ops/Automation-tool.git">
        <label for="githubToken">GitHub token</label>
        <input id="githubToken" type="password" placeholder="Fine-grained token with Contents read/write">
        <label><input id="githubAutoPublishMedia" type="checkbox" checked> Automatically publish generated media to GitHub</label>
        <label for="r2AccountId">Cloudflare R2 account ID</label>
        <input id="r2AccountId" placeholder="Cloudflare account ID">
        <label for="r2AccessKeyId">Cloudflare R2 access key ID</label>
        <input id="r2AccessKeyId" type="password" placeholder="Paste R2 access key ID here">
        <label for="r2SecretAccessKey">Cloudflare R2 secret access key</label>
        <input id="r2SecretAccessKey" type="password" placeholder="Paste R2 secret key here">
        <label for="r2Bucket">Cloudflare R2 bucket</label>
        <input id="r2Bucket" placeholder="Bucket name">
        <label for="r2PublicBaseUrl">Cloudflare R2 public media base URL</label>
        <input id="r2PublicBaseUrl" placeholder="https://your-public-r2-domain">
        <div class="row">
          <button id="saveSettingsBtn" type="button">Save Connection</button>
          <button id="findInstagramBtn" class="secondary" type="button">Find Account ID</button>
          <button id="testBufferBtn" class="secondary" type="button">Test Buffer</button>
          <button id="bufferChannelsBtn" class="secondary" type="button">Find Buffer Channels</button>
          <span id="settingsStatus" class="status"></span>
        </div>
      </details>
    </form>
    <section>
      <div id="status" class="status">Paste a chapter to create three promo images, captions, platform notes, and video helper files.</div>
      <div id="results"></div>
      <div class="examples">
        <h2>Examples found nearby</h2>
        <ul id="examples"><li>No scan run yet.</li></ul>
      </div>
    </section>
  </main>
  <script>
    const form = document.getElementById('promoForm');
    const statusEl = document.getElementById('status');
    const results = document.getElementById('results');
    const buildBtn = document.getElementById('buildBtn');
    const examples = document.getElementById('examples');
    const socialBtn = document.getElementById('socialBtn');
    const socialNovel = document.getElementById('socialNovel');
    const socialDay = document.getElementById('socialDay');
    const socialPrompt = document.getElementById('socialPrompt');
    const tiktokNovel = document.getElementById('tiktokNovel');
    const tiktokChapter = document.getElementById('tiktokChapter');
    const tiktokBtn = document.getElementById('tiktokBtn');
    const youtubeTextBtn = document.getElementById('youtubeTextBtn');
    const scheduleBtn = document.getElementById('scheduleBtn');
    const todayBtn = document.getElementById('todayBtn');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    const settingsStatus = document.getElementById('settingsStatus');
    const writeNovel = document.getElementById('writeNovel');
    const writeChapterBtn = document.getElementById('writeChapterBtn');
    let currentFolder = '';

    writeNovel.innerHTML = [
      ['EN', 'Eternal Nexus'],
      ['HA', 'Heavenly Ascension System'],
      ['SF', 'Soul Forge Era'],
      ['HP', 'Hundredfold Path']
    ].map(([abbr, name]) => `<option value="${name}">${abbr} - ${name}</option>`).join('');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const title = document.getElementById('title').value.trim();
      const chapter = document.getElementById('chapter').value.trim();
      if (!chapter) {
        statusEl.textContent = 'Paste a chapter first.';
        return;
      }
      buildBtn.disabled = true;
      statusEl.textContent = 'Building the promo pack...';
      results.innerHTML = '';
      try {
        const response = await fetch('/api/campaign', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title, chapter, useOpenAI: document.getElementById('useOpenAI').checked})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Build failed');
        renderResults(data);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        buildBtn.disabled = false;
      }
    });

    writeChapterBtn.addEventListener('click', async () => {
      writeChapterBtn.disabled = true;
      statusEl.textContent = 'Writing the chapter and building promo files...';
      results.innerHTML = '';
      try {
        const response = await fetch('/api/write-chapter', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            novel: writeNovel.value,
            chapterNumber: document.getElementById('writeChapterNumber').value.trim(),
            chapterTitle: document.getElementById('writeChapterTitle').value.trim(),
            outline: document.getElementById('writeOutline').value.trim(),
            continuity: document.getElementById('writeContinuity').value.trim(),
            targetWords: Number(document.getElementById('writeTargetWords').value || 3000)
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Chapter writing failed');
        renderWrittenChapter(data);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        writeChapterBtn.disabled = false;
      }
    });

    document.getElementById('scanBtn').addEventListener('click', async () => {
      examples.innerHTML = '<li>Scanning nearby folders...</li>';
      const response = await fetch('/api/examples');
      const data = await response.json();
      examples.innerHTML = data.examples.length ? data.examples.map(item => `<li title="${item.path}">${item.name}</li>`).join('') : '<li>No examples found nearby.</li>';
    });

    socialBtn.addEventListener('click', async () => {
      socialBtn.disabled = true;
      statusEl.textContent = 'Creating the Instagram/X post pack...';
      results.innerHTML = '';
      try {
        const response = await fetch('/api/social-post', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            abbr: socialNovel.value,
            day: socialDay.value,
            promptTemplate: socialPrompt.value,
            useOpenAI: document.getElementById('useOpenAI').checked
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Post build failed');
        renderSocialPost(data);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        socialBtn.disabled = false;
      }
    });

    async function loadSocialAssets() {
      const response = await fetch('/api/social-assets');
      const data = await response.json();
      socialPrompt.value = data.promptTemplate || '';
      const novels = [...new Map(data.items.map(item => [item.abbr, item])).values()];
      socialNovel.innerHTML = novels.map(item => `<option value="${item.abbr}">${item.abbr} - ${item.novel}</option>`).join('');
      socialDay.innerHTML = data.days.map(day => `<option value="${day}">${day}</option>`).join('');
      if (data.today && data.days.includes(data.today)) socialDay.value = data.today;
      if (!data.items.length) statusEl.textContent = 'No daily promo images were found in the Promo Images folder.';
      loadTikTokSelectors(data.tiktok || {imageGroups: [], sounds: []});
    }
    loadSocialAssets();

    function loadTikTokSelectors(tiktok) {
      const novels = [...new Map((tiktok.imageGroups || []).map(item => [item.abbr, item])).values()];
      tiktokNovel.innerHTML = novels.map(item => `<option value="${item.abbr}">${item.abbr} - ${item.novel}</option>`).join('');
      function refreshChapters() {
        const chapters = (tiktok.imageGroups || []).filter(item => item.abbr === tiktokNovel.value);
        tiktokChapter.innerHTML = chapters.map(item => `<option value="${item.chapter}">Chapter ${item.chapter}</option>`).join('');
        tiktokChapter.disabled = !chapters.length;
      }
      tiktokNovel.addEventListener('change', refreshChapters);
      refreshChapters();
    }

    tiktokBtn.addEventListener('click', async () => {
      tiktokBtn.disabled = true;
      statusEl.textContent = 'Creating the TikTok post pack...';
      results.innerHTML = '';
      try {
        const selectedChapter = tiktokChapter.value || document.getElementById('tiktokManualChapter').value.trim();
        const response = await fetch('/api/tiktok-post', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            abbr: tiktokNovel.value,
            chapter: selectedChapter,
            visualPrompt: document.getElementById('tiktokVisualPrompt').value.trim()
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'TikTok pack failed');
        renderTikTokPost(data);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        tiktokBtn.disabled = false;
      }
    });

    youtubeTextBtn.addEventListener('click', async () => {
      youtubeTextBtn.disabled = true;
      statusEl.textContent = 'Creating YouTube video files...';
      results.innerHTML = '';
      try {
        const response = await fetch('/api/youtube-text-video', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            title: document.getElementById('youtubeTitle').value.trim(),
            text: document.getElementById('youtubeText').value.trim()
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'YouTube video setup failed');
        renderYouTubeTextVideo(data);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        youtubeTextBtn.disabled = false;
      }
    });

    scheduleBtn.addEventListener('click', () => loadSchedule(false));
    todayBtn.addEventListener('click', () => loadSchedule(true));

    async function loadSchedule(todayOnly) {
      statusEl.textContent = todayOnly ? 'Loading today’s posts...' : 'Loading upcoming schedule...';
      results.innerHTML = '';
      const response = await fetch(todayOnly ? '/api/schedule?today=1' : '/api/schedule');
      const data = await response.json();
      if (!response.ok) {
        statusEl.textContent = data.error || 'Could not load schedule';
        return;
      }
      renderSchedule(data.tasks || [], todayOnly);
    }

    saveSettingsBtn.addEventListener('click', async () => {
      saveSettingsBtn.disabled = true;
      settingsStatus.textContent = 'Saving...';
      try {
        const response = await fetch('/api/settings', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            openaiApiKey: document.getElementById('openaiApiKey').value.trim(),
            instagramAccountId: document.getElementById('instagramAccountId').value.trim(),
            instagramAccessToken: document.getElementById('instagramAccessToken').value.trim(),
            instagramPublicBaseUrl: document.getElementById('instagramPublicBaseUrl').value.trim(),
            xAccessToken: document.getElementById('xAccessToken').value.trim(),
            bufferApiKey: document.getElementById('bufferApiKey').value.trim(),
            bufferPublicBaseUrl: document.getElementById('bufferPublicBaseUrl').value.trim(),
            bufferChannelIds: document.getElementById('bufferChannelIds').value.trim(),
            githubPagesMediaBaseUrl: document.getElementById('githubPagesMediaBaseUrl').value.trim(),
            githubRemoteUrl: document.getElementById('githubRemoteUrl').value.trim(),
            githubToken: document.getElementById('githubToken').value.trim(),
            githubAutoPublishMedia: document.getElementById('githubAutoPublishMedia').checked ? '1' : '0',
            r2AccountId: document.getElementById('r2AccountId').value.trim(),
            r2AccessKeyId: document.getElementById('r2AccessKeyId').value.trim(),
            r2SecretAccessKey: document.getElementById('r2SecretAccessKey').value.trim(),
            r2Bucket: document.getElementById('r2Bucket').value.trim(),
            r2PublicBaseUrl: document.getElementById('r2PublicBaseUrl').value.trim(),
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Settings save failed');
        settingsStatus.textContent = 'Saved locally.';
        document.getElementById('openaiApiKey').value = '';
        document.getElementById('instagramAccessToken').value = '';
        document.getElementById('xAccessToken').value = '';
        document.getElementById('bufferApiKey').value = '';
        document.getElementById('githubToken').value = '';
        document.getElementById('r2AccessKeyId').value = '';
        document.getElementById('r2SecretAccessKey').value = '';
      } catch (error) {
        settingsStatus.textContent = error.message;
      } finally {
        saveSettingsBtn.disabled = false;
      }
    });

    document.getElementById('findInstagramBtn').addEventListener('click', async () => {
      const btn = document.getElementById('findInstagramBtn');
      btn.disabled = true;
      settingsStatus.textContent = 'Looking for connected Instagram accounts...';
      try {
        const response = await fetch('/api/instagram-accounts');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not find accounts');
        const accounts = (data.data || []).flatMap(page => page.instagram_business_account ? [{page: page.name, ...page.instagram_business_account}] : []);
        if (!accounts.length) {
          settingsStatus.textContent = 'No connected Instagram business account found.';
          return;
        }
        document.getElementById('instagramAccountId').value = accounts[0].id;
        settingsStatus.textContent = `Found ${accounts[0].username || accounts[0].name || accounts[0].id}. Save Connection to keep it.`;
      } catch (error) {
        settingsStatus.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    });

    async function loadSettingsStatus() {
      const response = await fetch('/api/settings');
      const data = await response.json();
      const ready = data.instagramAccountId && data.instagramAccessToken;
      const xReady = data.xAccessToken;
      const bufferReady = data.bufferApiKey;
      const openaiReady = data.openaiApiKey;
      const githubReady = data.githubPagesMediaBaseUrl;
      const githubTokenReady = data.githubToken;
      document.getElementById('githubAutoPublishMedia').checked = data.githubAutoPublishMedia;
      const r2Ready = data.r2AccountId && data.r2AccessKeyId && data.r2SecretAccessKey && data.r2Bucket && data.r2PublicBaseUrl;
      settingsStatus.textContent = `${openaiReady ? 'OpenAI key saved.' : 'OpenAI not configured.'} ${ready ? 'Instagram token saved.' : 'Instagram not fully configured.'} ${xReady ? 'X token saved.' : 'X not configured.'} ${bufferReady ? 'Buffer key saved.' : 'Buffer not configured.'} ${githubReady ? 'GitHub media ready.' : 'GitHub media not configured.'} ${githubTokenReady ? 'GitHub token saved.' : 'GitHub token not configured.'} ${data.githubAutoPublishMedia ? 'Auto-publish on.' : 'Auto-publish off.'} ${r2Ready ? 'R2 ready.' : 'R2 not fully configured.'}`;
    }
    loadSettingsStatus();

    document.getElementById('bufferChannelsBtn').addEventListener('click', async () => {
      const btn = document.getElementById('bufferChannelsBtn');
      btn.disabled = true;
      settingsStatus.textContent = 'Loading Buffer channels...';
      try {
        const response = await fetch('/api/buffer-channels');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not load Buffer channels');
        renderBufferChannels(data.channels || []);
        settingsStatus.textContent = `Found ${(data.channels || []).length} Buffer channels.`;
      } catch (error) {
        settingsStatus.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById('testBufferBtn').addEventListener('click', async () => {
      const btn = document.getElementById('testBufferBtn');
      btn.disabled = true;
      settingsStatus.textContent = 'Testing Buffer connection...';
      try {
        const response = await fetch('/api/buffer-test');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Buffer test failed');
        settingsStatus.textContent = `Buffer connected. Found ${data.channelCount} channel(s).`;
        renderBufferChannels(data.channels || []);
      } catch (error) {
        settingsStatus.textContent = error.message;
        results.innerHTML = `<div class="copy"><strong>Buffer test failed</strong>\n${escapeHtml(error.message)}</div>`;
      } finally {
        btn.disabled = false;
      }
    });

    function fileUrl(path) {
      return '/file?path=' + encodeURIComponent(path);
    }

    function renderResults(data) {
      statusEl.textContent = data.source === 'openai' ? 'Promo pack created with OpenAI.' : 'Promo pack created with fallback image sources.';
      const cards = data.images.map((image, index) => `
        <article class="card">
          <img src="${fileUrl(image)}" alt="Promo image ${index + 1}">
          <p>${escapeHtml(data.phrases[index] || '')}</p>
        </article>
      `).join('');
      results.innerHTML = `
        <div class="grid">${cards}</div>
        <div class="copy">${escapeHtml(data.caption || '')}</div>
        <div class="copy">${escapeHtml(data.royal_road_note || '')}</div>
        <div class="copy">${escapeHtml(data.patreon_note || '')}</div>
        <div class="row">
          <button id="patreonAssistBtn" type="button">Manual Patreon Assist</button>
          <button id="patreonDoneBtn" class="secondary" type="button">Mark Patreon Posted</button>
          <button id="royalRoadAssistBtn" type="button">Manual Royal Road Assist</button>
          <button id="royalRoadDoneBtn" class="secondary" type="button">Mark Royal Road Posted</button>
          <button id="githubMediaBtn" class="secondary" type="button">Copy Media to GitHub</button>
        </div>
        <div class="copy"><strong>YouTube backgrounds</strong>\n${escapeHtml((data.background_videos || []).map(path => path.split(/[\\\\/]/).pop()).join('\n') || 'No background videos found.')}</div>
        <div class="row"><button id="youtubeBtn" type="button">Build YouTube Video</button></div>
        <div class="meta">Output folder: ${escapeHtml(data.folder)}</div>
      `;
      currentFolder = data.folder;
      document.getElementById('youtubeBtn').addEventListener('click', buildYoutube);
      document.getElementById('patreonAssistBtn').addEventListener('click', () => manualTextPlatformAssist('patreon'));
      document.getElementById('patreonDoneBtn').addEventListener('click', () => markTextPlatformPosted('patreon'));
      document.getElementById('royalRoadAssistBtn').addEventListener('click', () => manualTextPlatformAssist('royal-road'));
      document.getElementById('royalRoadDoneBtn').addEventListener('click', () => markTextPlatformPosted('royal-road'));
      document.getElementById('githubMediaBtn').addEventListener('click', copyMediaToGithub);
    }

    function renderWrittenChapter(data) {
      statusEl.textContent = 'Chapter written and promo pack created.';
      const preview = (data.chapter_text || '').slice(0, 1200);
      results.innerHTML = `
        <div class="copy"><strong>${escapeHtml(data.title || 'New Chapter')}</strong>\n\n${escapeHtml(preview)}${(data.chapter_text || '').length > 1200 ? '\n\n...' : ''}</div>
        <div class="copy"><strong>Summary</strong>\n${escapeHtml(data.short_summary || '')}</div>
        <div class="meta">Chapter folder: ${escapeHtml(data.folder)}</div>
        <div class="meta">Promo folder: ${escapeHtml(data.campaign?.folder || '')}</div>
      `;
      if (data.campaign) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = 'Show Generated Promo';
        btn.addEventListener('click', () => renderResults(data.campaign));
        const row = document.createElement('div');
        row.className = 'row';
        row.appendChild(btn);
        results.appendChild(row);
      }
    }

    async function buildYoutube() {
      const btn = document.getElementById('youtubeBtn');
      btn.disabled = true;
      statusEl.textContent = 'Building the YouTube video...';
      try {
        const response = await fetch('/api/youtube', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Video build failed');
        statusEl.textContent = data.created ? 'YouTube video created.' : 'Video builder finished, but no MP4 was created. Check youtube-project-notes.txt.';
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = data.message;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function manualTextPlatformAssist(platform) {
      const label = platform === 'patreon' ? 'Patreon' : 'Royal Road';
      statusEl.textContent = `Opening ${label} and copying prepared text...`;
      try {
        const response = await fetch('/api/text-platform-assist', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder, platform})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `${label} assist failed`);
        statusEl.textContent = data.message;
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = `${label} text copied from:\n${data.text_file}`;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    async function markTextPlatformPosted(platform) {
      const label = platform === 'patreon' ? 'Patreon' : 'Royal Road';
      statusEl.textContent = `Marking ${label} complete...`;
      try {
        const response = await fetch('/api/text-platform-posted', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder, platform})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || `Could not mark ${label} posted`);
        statusEl.textContent = `${label} marked complete.`;
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    function renderSocialPost(data) {
      statusEl.textContent = data.source === 'openai' ? 'Social post pack created with OpenAI.' : 'Social post pack created from the reusable fallback template.';
      results.innerHTML = `
        <div class="grid">
          <article class="card">
            <img src="${fileUrl(data.image)}" alt="${escapeHtml(data.alt_text || '')}">
            <p>${escapeHtml(data.abbr)} - ${escapeHtml(data.day)}</p>
          </article>
        </div>
        <div class="copy"><strong>Instagram</strong>\n${escapeHtml(data.instagram || '')}</div>
        <div class="copy"><strong>X</strong>\n${escapeHtml(data.x || '')}</div>
        <div class="copy"><strong>Alt text</strong>\n${escapeHtml(data.alt_text || '')}</div>
        <div class="row">
          <button id="manualXBtn" type="button">Manual X Assist</button>
          <button id="manualXDoneBtn" class="secondary" type="button">Mark X Posted</button>
          <button id="xPostBtn" class="secondary" type="button">API Post to X</button>
          <button id="bufferAssistSocialBtn" class="secondary" type="button">Manual Buffer Assist</button>
          <button id="bufferDoneSocialBtn" class="secondary" type="button">Mark Buffer Queued</button>
          <button id="githubMediaSocialBtn" class="secondary" type="button">Copy Media to GitHub</button>
        </div>
        <div class="row">
          <button id="manualInstagramBtn" type="button">Manual Instagram Assist</button>
          <button id="manualDoneBtn" class="secondary" type="button">Mark Posted</button>
          <button id="instagramBtn" class="secondary" type="button">API Post</button>
        </div>
        <div class="meta">Output folder: ${escapeHtml(data.folder)}</div>
      `;
      currentFolder = data.folder;
      document.getElementById('instagramBtn').addEventListener('click', publishInstagram);
      document.getElementById('manualInstagramBtn').addEventListener('click', manualInstagramAssist);
      document.getElementById('manualDoneBtn').addEventListener('click', markManualPosted);
      document.getElementById('manualXBtn').addEventListener('click', manualXAssist);
      document.getElementById('manualXDoneBtn').addEventListener('click', markManualXPosted);
      document.getElementById('xPostBtn').addEventListener('click', publishX);
      document.getElementById('bufferAssistSocialBtn').addEventListener('click', () => manualBufferAssist('instagram'));
      document.getElementById('bufferDoneSocialBtn').addEventListener('click', markBufferQueued);
      document.getElementById('githubMediaSocialBtn').addEventListener('click', copyMediaToGithub);
    }

    function renderTikTokPost(data) {
      statusEl.textContent = 'TikTok post pack created.';
      const cards = data.images.map((image, index) => `
        <article class="card">
          <img src="${fileUrl(image)}" alt="TikTok image ${index + 1}">
          <p>${escapeHtml(data.novel)} - Chapter ${escapeHtml(data.chapter)}</p>
        </article>
      `).join('');
      results.innerHTML = `
        <div class="grid">${cards}</div>
        <div class="copy"><strong>TikTok caption</strong>\n${escapeHtml(data.caption || '')}</div>
        <div class="copy"><strong>Selected sound</strong>\n${escapeHtml((data.sound || '').split(/[\\\\/]/).pop())}</div>
        <div class="row">
          <button id="tiktokAssistBtn" type="button">Manual TikTok Assist</button>
          <button id="tiktokDoneBtn" class="secondary" type="button">Mark TikTok Posted</button>
          <button id="tiktokVideoBtn" class="secondary" type="button">Build TikTok Video</button>
          <button id="bufferAssistTikTokBtn" class="secondary" type="button">Manual Buffer Assist</button>
          <button id="bufferDoneTikTokBtn" class="secondary" type="button">Mark Buffer Queued</button>
          <button id="githubMediaTikTokBtn" class="secondary" type="button">Copy Media to GitHub</button>
        </div>
        <div class="meta">Output folder: ${escapeHtml(data.folder)}</div>
      `;
      currentFolder = data.folder;
      document.getElementById('tiktokAssistBtn').addEventListener('click', manualTikTokAssist);
      document.getElementById('tiktokDoneBtn').addEventListener('click', markTikTokPosted);
      document.getElementById('tiktokVideoBtn').addEventListener('click', buildTikTokVideo);
      document.getElementById('bufferAssistTikTokBtn').addEventListener('click', () => manualBufferAssist('tiktok'));
      document.getElementById('bufferDoneTikTokBtn').addEventListener('click', markBufferQueued);
      document.getElementById('githubMediaTikTokBtn').addEventListener('click', copyMediaToGithub);
    }

    function renderYouTubeTextVideo(data) {
      statusEl.textContent = 'YouTube files created.';
      results.innerHTML = `
        <div class="copy"><strong>Title</strong>\n${escapeHtml(data.title || '')}</div>
        <div class="copy"><strong>Description</strong>\n${escapeHtml(data.description || '')}</div>
        <div class="copy"><strong>Tags</strong>\n${escapeHtml(data.tags || '')}</div>
        <div class="copy"><strong>Background videos</strong>\n${escapeHtml((data.background_videos || []).map(path => path.split(/[\\\\/]/).pop()).join('\n'))}</div>
        <div class="row">
          <button id="buildYoutubeTextBtn" type="button">Build MP4</button>
          <button id="bufferAssistYoutubeBtn" class="secondary" type="button">Manual Buffer Assist</button>
          <button id="bufferDoneYoutubeBtn" class="secondary" type="button">Mark Buffer Queued</button>
          <button id="githubMediaYoutubeBtn" class="secondary" type="button">Copy Media to GitHub</button>
        </div>
        <div class="meta">Output folder: ${escapeHtml(data.folder)}</div>
      `;
      currentFolder = data.folder;
      document.getElementById('buildYoutubeTextBtn').addEventListener('click', buildYoutubeTextMp4);
      document.getElementById('bufferAssistYoutubeBtn').addEventListener('click', () => manualBufferAssist('youtube'));
      document.getElementById('bufferDoneYoutubeBtn').addEventListener('click', markBufferQueued);
      document.getElementById('githubMediaYoutubeBtn').addEventListener('click', copyMediaToGithub);
    }

    async function buildYoutubeTextMp4() {
      const btn = document.getElementById('buildYoutubeTextBtn');
      btn.disabled = true;
      statusEl.textContent = 'Building YouTube MP4...';
      try {
        const response = await fetch('/api/youtube-text-build', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Build failed');
        statusEl.textContent = data.created ? 'YouTube MP4 created.' : 'Builder finished, but no MP4 was created.';
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = data.message;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    function renderSchedule(tasks, todayOnly) {
      statusEl.textContent = todayOnly ? `${tasks.length} posts due today.` : `${tasks.length} upcoming scheduled posts.`;
      if (!tasks.length) {
        results.innerHTML = '<div class="copy">No scheduled posts found for this view.</div>';
        return;
      }
      results.innerHTML = tasks.map(task => `
        <article class="card" style="margin-bottom:14px;">
          <p>${escapeHtml(task.date)} · ${escapeHtml(task.abbr)} · ${escapeHtml(task.platform)}${task.chapter ? ' · Chapter ' + escapeHtml(task.chapter) : ''}</p>
          <div class="copy"><strong>Instagram</strong>\n${escapeHtml(task.instagram || '')}</div>
          <div class="copy"><strong>X</strong>\n${escapeHtml(task.x || '')}</div>
        </article>
      `).join('');
    }

    function renderBufferChannels(channels) {
      results.innerHTML = `
        <div class="copy"><strong>Buffer Channels</strong>\n${escapeHtml(channels.map(channel => `${channel.service}: ${channel.name} (${channel.id})`).join('\n') || 'No channels found.')}</div>
      `;
    }

    async function manualTikTokAssist() {
      const btn = document.getElementById('tiktokAssistBtn');
      btn.disabled = true;
      statusEl.textContent = 'Opening TikTok and copying the caption...';
      try {
        const response = await fetch('/api/tiktok-manual-assist', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Manual TikTok assist failed');
        statusEl.textContent = data.message;
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function markTikTokPosted() {
      const btn = document.getElementById('tiktokDoneBtn');
      btn.disabled = true;
      statusEl.textContent = 'Marking TikTok complete...';
      try {
        const response = await fetch('/api/tiktok-manual-posted', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not mark TikTok posted');
        statusEl.textContent = 'TikTok post marked complete.';
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function buildTikTokVideo() {
      const btn = document.getElementById('tiktokVideoBtn');
      btn.disabled = true;
      statusEl.textContent = 'Building TikTok video...';
      try {
        const response = await fetch('/api/tiktok-video', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'TikTok video build failed');
        statusEl.textContent = data.created ? 'TikTok video created.' : 'Video builder finished, but no MP4 was created.';
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = data.message;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function manualXAssist() {
      const btn = document.getElementById('manualXBtn');
      btn.disabled = true;
      statusEl.textContent = 'Opening X and copying the post text...';
      try {
        const response = await fetch('/api/x-manual-assist', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Manual X assist failed');
        statusEl.textContent = data.message;
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = `Attach this image:\n${data.image}\n\nX text is copied to the clipboard.`;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function markManualXPosted() {
      const btn = document.getElementById('manualXDoneBtn');
      btn.disabled = true;
      statusEl.textContent = 'Marking the X post complete...';
      try {
        const response = await fetch('/api/x-manual-posted', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not mark X posted');
        statusEl.textContent = 'X post marked complete.';
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function publishX() {
      const btn = document.getElementById('xPostBtn');
      btn.disabled = true;
      statusEl.textContent = 'Posting to X...';
      try {
        const response = await fetch('/api/x-publish', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'X publish failed');
        statusEl.textContent = 'X post published.';
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = `X post id: ${data.post_response?.data?.id || 'created'}`;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function manualInstagramAssist() {
      const btn = document.getElementById('manualInstagramBtn');
      btn.disabled = true;
      statusEl.textContent = 'Opening Instagram and copying the caption...';
      try {
        const response = await fetch('/api/instagram-manual-assist', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Manual assist failed');
        statusEl.textContent = data.message;
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = `Select this image:\n${data.image}\n\nCaption is copied to the clipboard.`;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function markManualPosted() {
      const btn = document.getElementById('manualDoneBtn');
      btn.disabled = true;
      statusEl.textContent = 'Marking the post complete...';
      try {
        const response = await fetch('/api/instagram-manual-posted', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not mark posted');
        statusEl.textContent = 'Instagram post marked complete.';
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    async function queueBuffer(textKind) {
      statusEl.textContent = 'Sending post to Buffer...';
      try {
        const response = await fetch('/api/buffer-post', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder, textKind})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Buffer post failed');
        statusEl.textContent = 'Post queued in Buffer.';
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = JSON.stringify(data.posts || data, null, 2);
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    async function manualBufferAssist(textKind) {
      statusEl.textContent = 'Opening Buffer and copying the post text...';
      try {
        const response = await fetch('/api/buffer-manual-assist', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder, textKind})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Buffer assist failed');
        statusEl.textContent = data.message;
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = `Use Buffer's Google Drive/media picker, then paste the copied text.\nMedia folder:\n${data.folder}`;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    async function markBufferQueued() {
      statusEl.textContent = 'Marking Buffer queued...';
      try {
        const response = await fetch('/api/buffer-manual-queued', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not mark Buffer queued');
        statusEl.textContent = 'Buffer post marked queued.';
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    async function uploadR2() {
      statusEl.textContent = 'Uploading media to Cloudflare R2...';
      try {
        const response = await fetch('/api/r2-upload', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'R2 upload failed');
        statusEl.textContent = `Uploaded ${data.uploaded.length} media file(s) to R2.`;
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = data.uploaded.map(item => item.url).join('\n');
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    async function copyMediaToGithub() {
      statusEl.textContent = 'Publishing media to GitHub...';
      try {
        const response = await fetch('/api/github-media-publish', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'GitHub media copy failed');
        statusEl.textContent = `Published ${data.copied.length} media file(s) to GitHub.`;
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = data.copied.map(item => item.url).join('\n') || `Media folder:\n${data.media_dir}`;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    async function publishInstagram() {
      const btn = document.getElementById('instagramBtn');
      btn.disabled = true;
      statusEl.textContent = 'Posting to Instagram...';
      try {
        const response = await fetch('/api/instagram-publish', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: currentFolder})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Instagram publish failed');
        statusEl.textContent = 'Instagram post published.';
        const log = document.createElement('div');
        log.className = 'copy';
        log.textContent = `Instagram media id: ${data.media_id || data.publish_response?.id || 'created'}`;
        results.appendChild(log);
      } catch (error) {
        statusEl.textContent = error.message;
      } finally {
        btn.disabled = false;
      }
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
    }
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            data = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path == "/api/examples":
            self.send_json({"examples": find_examples()})
            return
        if parsed.path == "/api/social-assets":
            today = time.strftime("%A")
            self.send_json(
                {
                    "items": list_daily_promo_images(),
                    "days": DAYS,
                    "today": today,
                    "promptTemplate": social_prompt_template(),
                    "tiktok": list_tiktok_assets(),
                }
            )
            return
        if parsed.path == "/api/settings":
            self.send_json(env_presence())
            return
        if parsed.path == "/api/schedule":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                tasks = schedule_tasks_for() if query.get("today") else build_schedule(28)
                self.send_json({"tasks": tasks, "config": ensure_schedule_file()})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        if parsed.path == "/api/buffer-channels":
            try:
                data = buffer_channels()
                if not data.get("channels"):
                    data["channels"] = configured_buffer_channels()
                    data["source"] = "saved"
                self.send_json(data)
            except Exception as exc:
                saved = configured_buffer_channels()
                if saved:
                    self.send_json({"channels": saved, "source": "saved", "channelLookupError": str(exc)})
                else:
                    self.send_json({"error": str(exc)}, 500)
            return
        if parsed.path == "/api/buffer-test":
            data = buffer_connection_diagnostics()
            if data.get("errorType") == "network":
                data["powershellFallback"] = powershell_buffer_test()
            self.send_json(data, 200 if data.get("authenticated") else 500)
            return
        if parsed.path == "/api/instagram-accounts":
            try:
                self.send_json(discover_instagram_accounts())
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        if parsed.path == "/file":
            query = urllib.parse.parse_qs(parsed.query)
            path = Path(query.get("path", [""])[0]).resolve()
            allowed_roots = [OUTPUT_DIR.resolve(), ASSET_DIR.resolve(), SOCIAL_OUTPUT_DIR.resolve(), TIKTOK_OUTPUT_DIR.resolve()]
            if not any(str(path).startswith(str(root)) for root in allowed_roots) or not path.exists():
                self.send_error(404)
                return
            content_type = "image/svg+xml" if path.suffix == ".svg" else "image/png"
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path not in {
            "/api/campaign",
            "/api/write-chapter",
            "/api/youtube",
            "/api/youtube-text-video",
            "/api/youtube-text-build",
            "/api/social-post",
            "/api/instagram-publish",
            "/api/instagram-manual-assist",
            "/api/instagram-manual-posted",
            "/api/x-manual-assist",
            "/api/x-manual-posted",
            "/api/x-publish",
            "/api/tiktok-post",
            "/api/tiktok-manual-assist",
            "/api/tiktok-manual-posted",
            "/api/tiktok-video",
            "/api/text-platform-assist",
            "/api/text-platform-posted",
            "/api/buffer-post",
            "/api/buffer-manual-assist",
            "/api/buffer-manual-queued",
            "/api/r2-upload",
            "/api/github-media-copy",
            "/api/github-media-publish",
            "/api/settings",
        }:
            self.send_error(404)
            return
        try:
            body = read_json_body(self)
            if self.path == "/api/r2-upload":
                self.send_json(upload_folder_media_to_r2(str(body.get("folder") or "")))
                return
            if self.path == "/api/github-media-copy":
                self.send_json(copy_folder_media_to_github(str(body.get("folder") or "")))
                return
            if self.path == "/api/github-media-publish":
                self.send_json(publish_folder_media_to_github(str(body.get("folder") or "")))
                return
            if self.path == "/api/buffer-manual-assist":
                self.send_json(manual_buffer_assist(str(body.get("folder") or ""), str(body.get("textKind") or "instagram")))
                return
            if self.path == "/api/buffer-manual-queued":
                self.send_json(mark_buffer_queued(str(body.get("folder") or "")))
                return
            if self.path == "/api/buffer-post":
                channel_ids = [
                    value.strip()
                    for value in os.environ.get("BUFFER_CHANNEL_IDS", "").split(",")
                    if value.strip()
                ]
                if not channel_ids:
                    self.send_json({"error": "Add Buffer channel IDs in Connections first."}, 400)
                    return
                self.send_json(buffer_post_from_folder(str(body.get("folder") or ""), channel_ids, str(body.get("textKind") or "instagram")))
                return
            if self.path == "/api/write-chapter":
                result = write_chapter_with_openai(
                    str(body.get("novel") or "Untitled Novel"),
                    str(body.get("chapterNumber") or ""),
                    str(body.get("chapterTitle") or ""),
                    str(body.get("outline") or ""),
                    str(body.get("continuity") or ""),
                    int(body.get("targetWords") or 3000),
                )
                self.send_json(result)
                return
            if self.path == "/api/youtube-text-video":
                self.send_json(build_youtube_from_text(str(body.get("title") or ""), str(body.get("text") or "")))
                return
            if self.path == "/api/youtube-text-build":
                folder = Path(str(body.get("folder") or "")).resolve()
                if not str(folder).startswith(str(YOUTUBE_OUTPUT_DIR.resolve())):
                    self.send_json({"error": "YouTube folder is not valid."}, 400)
                    return
                script = folder / "build_youtube_video.py"
                if not script.exists():
                    self.send_json({"error": "This folder does not have a YouTube builder."}, 400)
                    return
                run = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                    timeout=1200,
                    check=False,
                )
                output = folder / "youtube-video.mp4"
                message = (run.stdout + "\n" + run.stderr).strip()
                self.send_json({"created": output.exists(), "video": str(output), "message": message or "Builder finished."})
                return
            if self.path == "/api/text-platform-assist":
                self.send_json(manual_text_platform_assist(str(body.get("folder") or ""), str(body.get("platform") or "")))
                return
            if self.path == "/api/text-platform-posted":
                self.send_json(mark_manual_text_platform_posted(str(body.get("folder") or ""), str(body.get("platform") or "")))
                return
            if self.path == "/api/tiktok-post":
                self.send_json(
                    make_or_generate_tiktok_pack(
                        str(body.get("abbr") or ""),
                        str(body.get("chapter") or ""),
                        str(body.get("visualPrompt") or ""),
                    )
                )
                return
            if self.path == "/api/tiktok-manual-assist":
                self.send_json(manual_tiktok_assist(str(body.get("folder") or "")))
                return
            if self.path == "/api/tiktok-manual-posted":
                self.send_json(mark_manual_tiktok_posted(str(body.get("folder") or "")))
                return
            if self.path == "/api/tiktok-video":
                folder = Path(str(body.get("folder") or "")).resolve()
                if not str(folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
                    self.send_json({"error": "TikTok folder is not valid."}, 400)
                    return
                script = folder / "make_tiktok_video.py"
                if not script.exists():
                    self.send_json({"error": "This TikTok pack does not have a video builder."}, 400)
                    return
                run = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
                output = folder / "tiktok-video.mp4"
                message = (run.stdout + "\n" + run.stderr).strip()
                self.send_json({"created": output.exists(), "video": str(output), "message": message or "Builder finished."})
                return
            if self.path == "/api/settings":
                values = {
                    "OPENAI_API_KEY": str(body.get("openaiApiKey") or "").strip(),
                    "INSTAGRAM_ACCOUNT_ID": str(body.get("instagramAccountId") or "").strip(),
                    "INSTAGRAM_ACCESS_TOKEN": str(body.get("instagramAccessToken") or "").strip(),
                    "INSTAGRAM_PUBLIC_BASE_URL": str(body.get("instagramPublicBaseUrl") or "").strip(),
                    "X_ACCESS_TOKEN": str(body.get("xAccessToken") or "").strip(),
                    "BUFFER_API_KEY": str(body.get("bufferApiKey") or "").strip(),
                    "BUFFER_PUBLIC_BASE_URL": str(body.get("bufferPublicBaseUrl") or "").strip(),
                    "BUFFER_CHANNEL_IDS": str(body.get("bufferChannelIds") or "").strip(),
                    "GITHUB_PAGES_MEDIA_BASE_URL": str(body.get("githubPagesMediaBaseUrl") or "").strip(),
                    "GITHUB_REMOTE_URL": str(body.get("githubRemoteUrl") or "").strip(),
                    "GITHUB_TOKEN": str(body.get("githubToken") or "").strip(),
                    "GITHUB_AUTO_PUBLISH_MEDIA": str(body.get("githubAutoPublishMedia") or "").strip(),
                    "CLOUDFLARE_R2_ACCOUNT_ID": str(body.get("r2AccountId") or "").strip(),
                    "CLOUDFLARE_R2_ACCESS_KEY_ID": str(body.get("r2AccessKeyId") or "").strip(),
                    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": str(body.get("r2SecretAccessKey") or "").strip(),
                    "CLOUDFLARE_R2_BUCKET": str(body.get("r2Bucket") or "").strip(),
                    "CLOUDFLARE_R2_PUBLIC_BASE_URL": str(body.get("r2PublicBaseUrl") or "").strip(),
                }
                upsert_env_values(values)
                self.send_json(env_presence())
                return
            if self.path == "/api/x-manual-assist":
                self.send_json(manual_x_assist(str(body.get("folder") or "")))
                return
            if self.path == "/api/x-manual-posted":
                self.send_json(mark_manual_x_posted(str(body.get("folder") or "")))
                return
            if self.path == "/api/x-publish":
                self.send_json(publish_x_post(str(body.get("folder") or "")))
                return
            if self.path == "/api/instagram-manual-assist":
                self.send_json(manual_instagram_assist(str(body.get("folder") or "")))
                return
            if self.path == "/api/instagram-manual-posted":
                self.send_json(mark_manual_instagram_posted(str(body.get("folder") or "")))
                return
            if self.path == "/api/instagram-publish":
                result = publish_instagram_image(str(body.get("folder") or ""))
                media_id = result.get("publish_response", {}).get("id")
                self.send_json({**result, "media_id": media_id})
                return
            if self.path == "/api/social-post":
                prompt_template = str(body.get("promptTemplate") or social_prompt_template())
                result = make_social_post(
                    str(body.get("abbr") or ""),
                    str(body.get("day") or ""),
                    prompt_template,
                    bool(body.get("useOpenAI", True)),
                )
                self.send_json(result)
                return
            if self.path == "/api/youtube":
                folder = Path(str(body.get("folder") or "")).resolve()
                if not str(folder).startswith(str(OUTPUT_DIR.resolve())):
                    self.send_json({"error": "Campaign folder is not valid."}, 400)
                    return
                script = folder / "make_youtube_video.py"
                if not script.exists():
                    self.send_json({"error": "This campaign does not have a YouTube builder."}, 400)
                    return
                run = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
                output = folder / "youtube-video.mp4"
                message = (run.stdout + "\n" + run.stderr).strip()
                self.send_json(
                    {
                        "created": output.exists(),
                        "video": str(output),
                        "message": message or "Builder finished.",
                    }
                )
                return
            title = str(body.get("title") or "Untitled Chapter")
            chapter = str(body.get("chapter") or "")
            if not chapter.strip():
                self.send_json({"error": "Chapter text is required."}, 400)
                return
            result = make_campaign(title, chapter, bool(body.get("useOpenAI", True)))
            self.send_json(result)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def log_message(self, format: str, *args: Any) -> None:
        return


def ensure_assets() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    ASSET_DIR.mkdir(exist_ok=True)
    SOCIAL_OUTPUT_DIR.mkdir(exist_ok=True)
    TIKTOK_OUTPUT_DIR.mkdir(exist_ok=True)
    CHAPTER_OUTPUT_DIR.mkdir(exist_ok=True)
    YOUTUBE_OUTPUT_DIR.mkdir(exist_ok=True)
    social_prompt_template()
    placeholder = ASSET_DIR / "placeholder.svg"
    if not placeholder.exists():
        placeholder.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1536" viewBox="0 0 1024 1536">
<rect width="1024" height="1536" fill="#172026"/>
<rect x="72" y="72" width="880" height="1392" rx="22" fill="#f7f9fb"/>
<text x="512" y="710" font-family="Arial, Helvetica, sans-serif" font-size="54" font-weight="700" fill="#172026" text-anchor="middle">Promo Image</text>
<foreignObject x="140" y="780" width="744" height="360">
<div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial, Helvetica, sans-serif;font-size:42px;line-height:1.2;text-align:center;color:#24313a;">{{PHRASE}}</div>
</foreignObject>
</svg>""",
            encoding="utf-8",
        )


def main() -> None:
    load_env_file()
    ensure_assets()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Chapter Promo Builder running at http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.")


if __name__ == "__main__":
    main()
