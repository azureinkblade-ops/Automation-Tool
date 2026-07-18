"""Hermes-authored story-hook packs (replaces the ChatGPT/CDP browser scrape).

This is a file-boundary integration (Codex pattern): the app shells out to the
Hermes CLI to generate the story-hook script text, exactly like
``agent_post_writer.py`` does for post copy. The output is written to the same
``STORY_HOOK_RESULT_FILE`` shape the Playwright/ChatGPT path uses, so the rest of
the pipeline (parse -> build_story_hook_video_files -> diffusers thumbnail) is
untouched.

Why this exists: the ChatGPT path required a signed-in ChatGPT tab driven over
Chrome DevTools (connectOverCDP), which is fragile (the 9222 endpoint stalls when
Chrome is in a bad state). Hermes generates the same JSON locally and gives more
per-novel variability because it can read the research brief directly.

Fail-soft: any error writes ``{ok: False, error}`` to the result file and returns
None, so the caller can fall back to the ChatGPT path or report failure.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# --- Hermes CLI resolution (mirrors agent_post_writer.py) -------------------
def _resolve_hermes() -> str | None:
    env = os.environ.get("HERMES_CLI", "").strip()
    if env and Path(env).exists():
        return env
    # Common locations: bundled .exe, then on PATH.
    candidates = [
        Path.home() / "AppData" / "Local" / "hermes" / "hermes.exe",
        Path("hermes.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    from shutil import which

    found = which("hermes") or which("hermes.exe")
    return found


# --- Research brief (per-novel voice + variability) -------------------------
_RESEARCH_BRIEF_FOLDER = os.environ.get(
    "RESEARCH_BRIEF_PATH",
    str(Path.home() / "Documents" / "Hermes Vault" / "Hermes" / "Research Briefs"),
)
_RESEARCH_BRIEF_FILE = os.environ.get("RESEARCH_BRIEF_FILE", "")

_NOVEL_TITLES = {
    "EN": "Eternal Nexus",
    "HA": "Heavenly Ascension System",
    "SF": "Soul Forge Era",
    "HP": "Hundredfold Path",
}

# Hermes vault base for per-pack capture.
_VAULT_BASE = os.environ.get(
    "HERMES_VAULT_BASE",
    str(Path.home() / "Documents" / "Hermes Vault" / "Hermes"),
)
_VAULT_STORY_HOOKS_DIR = Path(_VAULT_BASE) / "Story Hooks"


def _brief_for_abbr(abbr: str) -> str:
    if _RESEARCH_BRIEF_FILE:
        return _RESEARCH_BRIEF_FILE
    folder = Path(_RESEARCH_BRIEF_FOLDER)
    if not folder.is_dir():
        return ""
    abbr = (abbr or "").upper().strip()
    title = _NOVEL_TITLES.get(abbr, abbr)
    for c in [
        folder / f"{abbr} — {title}.md",
        folder / f"{title}.md",
        folder / f"{abbr}.md",
    ]:
        if c.exists():
            return str(c)
    return ""


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or "story-hook"


def _build_prompt(abbr: str, angle: str, target_words: int, base_prompt: str, brief_text: str) -> str:
    novel = _NOVEL_TITLES.get(abbr.upper(), abbr)
    brief_excerpt = (brief_text or "").strip()
    if len(brief_excerpt) > 4000:
        brief_excerpt = brief_excerpt[:4000] + "\n...[brief truncated]"
    return f"""{base_prompt}

PER-NOVEL RESEARCH BRIEF (voice, audience language, hook angles, tone, banned
phrases — follow it strictly so this pack sounds like {novel}, not a generic
AI script, and never borrows another novel's voice):
{brief_excerpt or "(no brief provided — use the novel name and general progression-fantasy voice)"}

Return ONLY a JSON object (no markdown fence, no commentary) with these exact keys:
  "title": clickable YouTube title under 90 characters,
  "story": full narration script ({target_words} words),
  "description": short YouTube description with Royal Road, Patreon, YouTube, TikTok, Instagram, and X links,
  "tags": array of 8 to 15 search tags,
  "relatedNovel": "{abbr}",
  "hookAngle": "{angle}"
"""


def _extract_json(text: str) -> dict | None:
    cleaned = "\n".join(
        ln for ln in text.splitlines() if not ln.strip().startswith("session_id:")
    ).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    if "```" in cleaned:
        start = cleaned.find("```")
        end = cleaned.find("```", start + 3)
        if end > start:
            inner = cleaned[start + 3 : end].lstrip("json").strip()
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass
    fb, lb = cleaned.find("{"), cleaned.rfind("}")
    if fb != -1 and lb > fb:
        try:
            return json.loads(cleaned[fb : lb + 1])
        except json.JSONDecodeError:
            pass
    return None


def _write_vault_pack(abbr: str, data: dict, folder: str) -> str | None:
    """Persist the built pack into the Obsidian vault so each pack is captured.

    Returns the vault note path, or None on failure. Failures are non-fatal.
    """
    try:
        _VAULT_STORY_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
        novel = _NOVEL_TITLES.get(abbr.upper(), abbr)
        title = str(data.get("title") or "Untitled Story Hook")
        note = _VAULT_STORY_HOOKS_DIR / f"{abbr} — {title[:50]}.md"
        lines = [
            "---",
            f"tags: [story-hook, {_slug(abbr)}, azure-inkblade]",
            "---",
            "",
            f"# {title}",
            "",
            f"**Novel:** {novel} ({abbr})",
            f"**Angle:** {data.get('hookAngle') or ''}",
            f"**App pack folder:** {folder}",
            f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Source:** Hermes",
            "",
            "## Story",
            "",
            str(data.get("story") or ""),
            "",
            "## Description",
            "",
            str(data.get("description") or ""),
            "",
            "## Tags",
            "",
            ", ".join(str(t) for t in (data.get("tags") or [])),
            "",
        ]
        note.write_text("\n".join(lines), encoding="utf-8")
        return str(note)
    except Exception:
        return None


def generate_and_write(
    abbr: str,
    angle: str,
    target_words: int,
    base_prompt: str,
    result_file: Path,
    *,
    skills: str = "ai-model-prompt-engineer,seo-audience-research",
    timeout: int = 300,
    max_turns: int = 6,
) -> dict | None:
    """Generate the story hook via Hermes and write ``STORY_HOOK_RESULT_FILE``.

    Writes the SAME shape the Playwright/ChatGPT script writes:
    ``{ok, storyText, wordCount, sourceUrl, completedAt}`` so the existing
    ``story_hook_video_worker`` parse/build path is unchanged.

    Returns the result dict on success, or ``{ok: False, error}`` (also written
    to disk) on any failure so the caller can fall back to ChatGPT.
    """
    hermes = _resolve_hermes()
    if not hermes:
        _fail(result_file, "hermes CLI not resolvable")
        return None
    brief_path = _brief_for_abbr(abbr)
    brief_text = ""
    if brief_path and Path(brief_path).exists():
        try:
            brief_text = Path(brief_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            brief_text = ""
    prompt = _build_prompt(abbr, angle, target_words, base_prompt, brief_text)

    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["HERMES_QUIET"] = "1"
    try:
        proc = subprocess.run(
            [hermes, "chat", "-q", prompt, "-s", skills, "-Q", "--max-turns", str(max_turns)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            cwd=str(Path.cwd()),
        )
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        _fail(result_file, f"subprocess error: {exc!r}")
        return None
    if proc.returncode != 0:
        _fail(result_file, f"hermes rc={proc.returncode}: {proc.stderr[:800]}")
        return None

    data = _extract_json(proc.stdout)
    if not isinstance(data, dict) or not str(data.get("story") or "").strip():
        _fail(result_file, f"output not parseable as story JSON: {proc.stdout[:800]}")
        return None

    story_text = json.dumps(data, ensure_ascii=False)
    result = {
        "ok": True,
        "jobId": os.environ.get("STORY_HOOK_JOB_ID", "hermes"),
        "storyText": story_text,
        "wordCount": len(str(data.get("story") or "").split()),
        "sourceUrl": "hermes",
        "completedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result


def _fail(result_file: Path, error: str) -> None:
    try:
        result_file.write_text(
            json.dumps(
                {"ok": False, "error": error, "completedAt": time.strftime("%Y-%m-%dT%H:%M:%S")},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
