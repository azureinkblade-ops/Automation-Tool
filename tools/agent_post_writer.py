"""Agent-driven post copy writer.

Wraps the headless Hermes CLI (`hermes.exe chat -q ... -Q --max-turns N`) to produce
reader-facing, research-aware social post copy per novel, replacing the template
engine's prose. Consumed by `promo_copy.build_platform_posts` via `agent_copy=`.

Design rules (mirrors the Codex file-boundary pattern + the app's fail-loud rule):
- The agent reads a per-novel RESEARCH BRIEF (Markdown) the app passes in. It never
  touches app internals.
- Output is the post-differentiation-agent JSON contract:
  {hook, caption, cta, hashtags (array), content_angle, intended_audience, ...}.
- On ANY failure (CLI missing, timeout, unparseable output) -> return None so the
  caller falls back to the existing `build_platform_posts()` template engine. Posts
  never break.
- The Hermes venv leaks a broken numpy onto sys.path via PYTHONPATH/PYTHONHOME; the
  subprocess MUST strip those (same class of bug as the LoRA trainer / diffusers).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Diagnostics: every agent failure (rc!=0, unparseable output, subprocess error) is
# logged here with the raw Hermes stdout/stderr so a failed post-build is diagnosable
# instead of silently falling back to the template. The app's own logs/ dir.
_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "agent_post_writer.log"
try:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(_LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
    _logger = logging.getLogger("agent_post_writer")
except OSError:
    _logger = logging.getLogger("agent_post_writer")
    _logger.addHandler(logging.NullHandler())


def _log(msg: str, *, abbr: str = "", stdout: str = "", stderr: str = "") -> None:
    """Record a diagnostic line (with raw agent output on failure) to logs/agent_post_writer.log."""
    tail = ""
    if stdout:
        tail += f"\n  STDOUT>>> {stdout!r}"
    if stderr:
        tail += f"\n  STDERR>>> {stderr!r}"
    _logger.error("[%s] %s%s", abbr or "-", msg, tail)


# Hermes CLI lives in its own venv; resolve from the known location, else PATH.
_HERMES_DEFAULT = (
    Path.home()
    / "AppData"
    / "Local"
    / "hermes"
    / "hermes-agent"
    / "venv"
    / "Scripts"
    / "hermes.exe"
)

# Per-novel research brief folder. Override with RESEARCH_BRIEF_PATH (a folder) or
# RESEARCH_BRIEF_FILE (an explicit file). The app points this at the Obsidian vault.
_RESEARCH_BRIEF_FOLDER = os.environ.get(
    "RESEARCH_BRIEF_PATH",
    str(Path.home() / "Documents" / "Hermes Vault" / "Hermes" / "Research Briefs"),
)
_RESEARCH_BRIEF_FILE = os.environ.get("RESEARCH_BRIEF_FILE", "")

_DEFAULT_SKILLS = "post-differentiation-agent,seo-audience-research"

# Novel title lookup so the brief filename / prompt can name the novel correctly.
_NOVEL_TITLES = {
    "EN": "Eternal Nexus",
    "HA": "Heavenly Ascension System",
    "SF": "Soulforge Era",
    "HP": "Hundredfold Path",
}


def _resolve_hermes() -> str | None:
    if _HERMES_DEFAULT.exists():
        return str(_HERMES_DEFAULT)
    found = shutil.which("hermes")
    return found


def _brief_for_abbr(abbr: str) -> str:
    """Return the path to the per-novel research brief, or '' if none resolvable."""
    if _RESEARCH_BRIEF_FILE:
        return _RESEARCH_BRIEF_FILE
    folder = Path(_RESEARCH_BRIEF_FOLDER)
    if not folder.is_dir():
        return ""
    abbr = (abbr or "").upper().strip()
    title = _NOVEL_TITLES.get(abbr, abbr)
    # Try "ABBR — Title.md" then a few fallbacks.
    candidates = [
        folder / f"{abbr} — {title}.md",
        folder / f"{title}.md",
        folder / f"{abbr}.md",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


def _build_prompt(abbr: str, title: str, chapter: str, hook: str, brief_text: str, material: dict) -> str:
    novel = _NOVEL_TITLES.get(abbr.upper(), title or abbr)
    release_status = material.get("release_status") or {}
    rr_live = bool(release_status.get("royalRoadExists"))
    focus = material.get("post_focus_override") or ""
    brief_excerpt = (brief_text or "").strip()
    if len(brief_excerpt) > 4000:
        brief_excerpt = brief_excerpt[:4000] + "\n...[brief truncated]"

    return f"""You are the post-differentiation agent for the web novel "{novel}".
Write ONE reader-facing social post for Instagram (the app reuses it for X/FB with
platform tails). The copy must speak TO the reader, never ABOUT the post or marketing.

NOVEL: {novel} (abbr {abbr})
CHAPTER: {chapter or "unknown"}
CHAPTER HOOK (real teaser from the chapter): {hook or "(none provided)"}
ROYAL ROAD LIVE: {"yes" if rr_live else "no"}
POST FOCUS: {focus or "default"}

PER-NOVEL RESEARCH BRIEF (voice, audience language, hook angles, CTA phrasings,
allowed/banned hashtags — follow it strictly, especially the banned-hashtag set so
this novel never borrows another novel's voice):
{brief_excerpt or "(no brief provided — use the novel name and general progression-fantasy voice)"}

Return ONLY a JSON object (no markdown fence, no commentary) with these keys:
- "hook": a 1-line reader hook (may reuse or sharpen the chapter hook above)
- "caption": the post BODY only (2-4 sentences, reader-facing, novel-specific).
  Do NOT include the call-to-action in the caption — the app appends "cta" separately,
  so repeating it here would duplicate it.
- "cta": a single call-to-action line (e.g. "Start {novel} here: <link>" or
  "Add {novel} to your weekend reading queue."). One line, no repetition.
- "hashtags": an array of 6-9 hashtags (must include the novel tag + #AzureInkblade;
  respect the brief's banned set)
- "content_angle": one short phrase naming the angle you chose
- "intended_audience": one short phrase

Do NOT mention "this post", "caption", "hashtags", or the marketing strategy.
The caption and cta together form one post — keep each distinct so nothing is repeated.
"""


def _strip_session_line(text: str) -> str:
    """Drop the `session_id: ...` line Hermes quietly appends in -Q mode."""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("session_id:")]
    return "\n".join(lines).strip()


def _extract_json(text: str) -> dict | None:
    """Parse JSON from the agent output, tolerating a prose wrapper, ```fence,
    and the malformed JSON the model occasionally emits (unquoted keys, trailing
    commas, inline // comments, stray adjacent quotes). Falls back to None only
    when the output is unrecoverable (e.g. truncated mid-object).

    Hermes sometimes returns almost-valid JSON rather than clean JSON; a tolerant
    repair step recovers those parses instead of silently degrading to the template.
    """
    cleaned = _strip_session_line(text)
    # 1) Direct parse (most outputs are already valid JSON).
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # 2) Fenced block (```json ... ```).
    if "```" in cleaned:
        start = cleaned.find("```")
        end = cleaned.find("```", start + 3)
        if end > start:
            inner = cleaned[start + 3 : end].lstrip("json").strip()
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass
    # 3) Slice first { to last }. If the object is truncated (no closing brace,
    #    or the braces are unbalanced) this yields nothing -> unrecoverable.
    fb = cleaned.find("{")
    lb = cleaned.rfind("}")
    if fb == -1 or lb <= fb:
        return None
    body = cleaned[fb : lb + 1]
    # --- stdlib repair passes (no external dependency required) ---
    # Strip // comments that are NOT part of a URL (protect http(s)://).
    body = re.sub(r"(?<!:)//[^\n]*", "", body)
    # Collapse runs of adjacent double-quotes (e.g. `{ ""hook":` -> `{ "hook":`).
    body = re.sub(r'"{2,}', '"', body)
    # Quote unquoted bare keys: { or , followed by an identifier then ':'.
    body = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', body)
    # Remove trailing commas before } or ].
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    # 4) Optional boost: json5 (installed in the codex runtime) tolerates the
    #    remaining edge cases. Not required — absent json5, we fall back to None.
    try:
        import json5

        return json5.loads(body)
    except Exception:
        return None


def _unwrap_variation(payload: dict | None) -> dict | None:
    """Normalize the agent's output into the flat consumer contract.

    The agent (post-differentiation-agent skill) may emit EITHER:
      * the flat legacy contract: {"hook", "caption", "cta", "hashtags",
        "content_angle", "intended_audience"} at the top level, OR
      * the skill's wrapped contract: {"generated_at", "agent",
        "variations": [ {...}, ... ]} where each variation carries the same fields.
    The consumer (promo_copy.build_platform_posts) only reads the flat keys, so we
    normalize the wrapped form down to one variation. Fails closed (None) when the
    payload has no usable caption (missing/empty variations, or no caption).
    """
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("variations"), list) and payload["variations"]:
        candidate = None
        for v in payload["variations"]:
            if isinstance(v, dict) and v.get("caption"):
                candidate = v
                break
        if candidate is None:
            return None
        src = candidate
    elif isinstance(payload, dict) and payload.get("caption"):
        src = payload
    else:
        return None
    tags = src.get("hashtags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
    out = {
        "hook": str(src.get("hook") or "").strip(),
        "caption": str(src.get("caption") or "").strip(),
        "cta": str(src.get("cta") or "").strip(),
        "hashtags": [str(t) for t in tags],
        "content_angle": str(src.get("content_angle") or "").strip(),
        "intended_audience": str(src.get("intended_audience") or "").strip(),
    }
    if not out["caption"]:
        return None
    out["_source"] = "hermes_agent"
    return out


def generate_post_copy(
    abbr: str,
    title: str,
    chapter: str,
    hook: str,
    material: dict | None = None,
    *,
    skills: str = _DEFAULT_SKILLS,
    timeout: int = 180,
    max_turns: int = 4,
) -> dict | None:
    """Return the agent's post copy dict, or None to signal 'fall back to template'.

    Never raises — any failure returns None so the caller uses build_platform_posts().
    """
    material = material or {}
    hermes = _resolve_hermes()
    if not hermes:
        _log("FAIL: hermes CLI not resolvable", abbr=abbr)
        return None
    brief_path = _brief_for_abbr(abbr)
    brief_text = ""
    if brief_path and Path(brief_path).exists():
        try:
            brief_text = Path(brief_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            brief_text = ""
    prompt = _build_prompt(abbr, title, chapter, hook, brief_text, material)

    # Strip the Hermes venv leak (broken numpy) + suppress banner/spinner.
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
        _log(f"FAIL: subprocess error: {exc!r}", abbr=abbr)
        return None
    if proc.returncode != 0:
        _log(
            f"FAIL: hermes rc={proc.returncode}",
            abbr=abbr,
            stdout=proc.stdout[:2000],
            stderr=proc.stderr[:2000],
        )
        return None
    data = _extract_json(proc.stdout)
    # Normalize to the flat consumer contract. Accepts both the wrapped skill
    # output ({"variations":[...]}) and the legacy flat response. None => fall
    # back to the template engine (the caller treats None as "use template").
    normalized = _unwrap_variation(data)
    if normalized is None:
        _log(
            "FAIL: output not parseable as post JSON (missing caption / empty or malformed variations)",
            abbr=abbr,
            stdout=proc.stdout[:3000],
            stderr=proc.stderr[:1500],
        )
        return None
    return normalized


if __name__ == "__main__":
    # Smoke test: python tools/agent_post_writer.py HA "Ch 24" "Kai's golden ember flares."
    _a = (sys.argv[1] if len(sys.argv) > 1 else "HA")
    _t = (sys.argv[2] if len(sys.argv) > 2 else "Ch 24")
    _h = (sys.argv[3] if len(sys.argv) > 3 else "")
    _out = generate_post_copy(_a, _t, _t, _h, {})
    print(json.dumps(_out, indent=2, ensure_ascii=False) if _out else "NULL (fallback)")
