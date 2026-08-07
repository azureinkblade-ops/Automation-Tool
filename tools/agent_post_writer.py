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
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class AgentPostStatus(str, Enum):
    """Terminal outcome of a single agent-post attempt (outcome only, not a phase)."""

    SUCCESS = "SUCCESS"
    HERMES_NOT_ENABLED = "HERMES_NOT_ENABLED"
    HERMES_NOT_STARTED = "HERMES_NOT_STARTED"
    HERMES_TIMEOUT = "HERMES_TIMEOUT"
    HERMES_PROCESS_FAILED = "HERMES_PROCESS_FAILED"
    HERMES_EMPTY_OUTPUT = "HERMES_EMPTY_OUTPUT"
    FINAL_BLOCK_NOT_FOUND = "FINAL_BLOCK_NOT_FOUND"
    JSON_PARSE_FAILED = "JSON_PARSE_FAILED"
    CONTRACT_VALIDATION_FAILED = "CONTRACT_VALIDATION_FAILED"
    DATABASE_PERSIST_FAILED = "DATABASE_PERSIST_FAILED"


@dataclass(frozen=True)
class HermesExecution:
    """Provenance of a single Hermes invocation (observed, never pinned)."""

    command_flags: tuple[str, ...]
    exit_code: int | None
    duration_ms: int
    started_at: str
    completed_at: str
    requested_model: str | None = None
    requested_provider: str | None = None
    resolved_model: str = "unknown"
    resolved_provider: str = "unknown"
    reasoning: str = "(default)"
    skills: str = ""
    quiet: bool = True
    max_turns: str = "(default 500)"
    session_mode: str = "fresh"
    session_id: str = ""
    stdout_replacement_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class AgentPostResult:
    """Full, structured result of an agent-post attempt.

    `status` is the only terminal signal. Diagnostics (parse_mode, normalizations,
    validation_errors, missing_fields, block counts) describe HOW an outcome was
    reached and are recorded even on failure. Never bare None.
    """

    status: AgentPostStatus
    copy: dict[str, Any] | None
    raw_response_path: Path | None
    run_id: str = ""
    parse_mode: str | None = None
    normalizations: tuple[str, ...] = ()
    validation_errors: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    final_block_count: int = 0
    selected_candidate_index: int | None = None
    fallback_reason: str | None = None
    execution: HermesExecution | None = None

# Diagnostics: every agent failure (rc!=0, unparseable output, subprocess error) is
# logged here with the raw Hermes stdout/stderr so a failed post-build is diagnosable
# instead of silently falling back to the template. The app's own logs/ dir.
#
# This module uses a dedicated, isolated logger. It must NOT call logging.basicConfig
# (which would hijack the process-wide root handler and pollute unrelated application
# logs). All agent diagnostics stay in logs/agent_post_writer.log only.
_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "agent_post_writer.log"
_logger = logging.getLogger("automation.agent_post_writer")
_logger.setLevel(logging.INFO)
_logger.propagate = False
if not _logger.handlers:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
        _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(_handler)
    except OSError:
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
    """Drop the `session_id: ...` line Hermes quietly appends.

    NOTE: session_id arrives on STDERR in -Q mode, not stdout. This helper is
    applied to stderr only; it must NOT be applied to stdout (the candidate
    model content), or it would never match and would be a no-op anyway.
    """
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("session_id:")]
    return "\n".join(lines).strip()


def _find_balanced_json_objects(text: str) -> list[str]:
    """Return every maximal balanced {...} substring in `text`, individually.

    Never spans candidates. A substring is balanced when every '{' has a matching
    '}' at the same nesting depth. Empty or truncated objects are excluded.
    """
    objects: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    body = text[start : i + 1]
                    objects.append(body)
                    start = -1
    return objects


def _repair_json_body(body: str) -> tuple[str | None, tuple[str, ...]]:
    """Attempt tolerant repair of an almost-valid JSON object body.

    Returns (repaired_text, normalizations). normalizations is a tuple of labels
    describing which repairs were applied. Returns (None, ()) when repair fails.
    """
    normalizations: list[str] = []
    candidate = body
    # Strip // comments that are NOT part of a URL (protect http(s)://).
    stripped = re.sub(r"(?<!:)//[^\n]*", "", candidate)
    if stripped != candidate:
        normalizations.append("removed_line_comment")
        candidate = stripped
    # Collapse runs of adjacent double-quotes (e.g. `{ ""hook":` -> `{ "hook":`).
    collapsed = re.sub(r'"{2,}', '"', candidate)
    if collapsed != candidate:
        normalizations.append("collapsed_double_quotes")
        candidate = collapsed
    # Quote unquoted bare keys: { or , followed by an identifier then ':'.
    quoted = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', candidate)
    if quoted != candidate:
        normalizations.append("quoted_bare_keys")
        candidate = quoted
    # Remove trailing commas before } or ].
    trimmed = re.sub(r",(\s*[}\]])", r"\1", candidate)
    if trimmed != candidate:
        normalizations.append("removed_trailing_comma")
        candidate = trimmed
    # Quote unquoted hashtag array elements. Observed Hermes defect: a hashtag
    # element with a trailing quote but no opening quote, e.g. `#AzureInkblade"`.
    # Also handle a fully-unquoted element `#Cyberpunk`. Repair is scoped to ARRAY
    # CONTEXT only (a `[` or `,` immediately precedes the `#`), so it can never
    # touch a properly-quoted string's interior content. Syntax only; the tag
    # text itself is preserved verbatim.
    quoted_tags = re.sub(
        r'([\[,]\s*)#([A-Za-z0-9_]+)"([\],])',
        r'\1"#\2"\3',
        candidate,
    )
    if quoted_tags != candidate:
        normalizations.append("quoted_unquoted_hashtag_elements")
        candidate = quoted_tags
    # Fully-unquoted hashtag element (no quotes at all) inside an array.
    fully_unquoted = re.sub(
        r'([\[,]\s*)#([A-Za-z0-9_]+)([,\]])',
        r'\1"#\2"\3',
        candidate,
    )
    if fully_unquoted != candidate:
        if "quoted_unquoted_hashtag_elements" not in normalizations:
            normalizations.append("quoted_unquoted_hashtag_elements")
        candidate = fully_unquoted
    try:
        json.loads(candidate)
        return candidate, tuple(normalizations)
    except json.JSONDecodeError:
        pass
    # Optional boost: json5 (installed in the codex runtime) tolerates the
    # remaining edge cases. Not required — absent json5, we fall back to None.
    try:
        import json5

        json5.loads(candidate)
        return candidate, tuple(normalizations)
    except Exception:
        return None, ()


def _looks_like_draft(markup: str) -> bool:
    """Detect draft/analysis contamination inside a candidate block."""
    lowered = markup.lower()
    markers = (
        "draft:",
        "corrected draft:",
        "wait,",
        "final check:",
        "**image_prompt**",
        "**variations**",
        "**reasoning",
        "_metadata_",
    )
    return any(m in lowered for m in markers)


def _extract_json(stdout_text: str) -> tuple[dict | None, str | None, tuple[str, ...]]:
    """Select the final usable JSON payload from Hermes stdout.

    Selection order (per the reliability plan, Task 4):
      1. Last complete fenced JSON object.
      2. Last complete balanced JSON object passing the contract.
      3. Failure (None) with diagnostics recorded by the caller.

    NEVER slices first-brace-to-last-brace across candidates. Each balanced object
    is evaluated individually. The selected block must not contain draft/analysis
    markers.

    Returns `(payload, parse_mode, normalizations)` where `parse_mode` is one of
    "whole_text" | "fenced_json" | "balanced_repair", or None when no usable block
    exists. `normalizations` records the repairs applied on the balanced_repair
    path (empty otherwise), so a repaired parse stays diagnosable.
    """
    # 1) Direct whole-text parse (most outputs are already valid JSON).
    # Reject outright if the whole response is a draft/analysis section.
    if not _looks_like_draft(stdout_text):
        try:
            return json.loads(stdout_text.strip()), "whole_text", ()
        except json.JSONDecodeError:
            pass
    # 2) Fenced block (```json ... ```). Take the LAST complete fence.
    if "```" in stdout_text:
        fences = []
        idx = stdout_text.find("```")
        while idx != -1:
            end = stdout_text.find("```", idx + 3)
            if end == -1:
                break
            inner = stdout_text[idx + 3 : end].lstrip("json").strip()
            fences.append(inner)
            idx = stdout_text.find("```", end + 3)
        for inner in reversed(fences):
            if _looks_like_draft(inner):
                continue
            try:
                return json.loads(inner), "fenced_json", ()
            except json.JSONDecodeError:
                pass
    # 3) Last complete balanced {...} object that parses and is not a draft.
    objects = _find_balanced_json_objects(stdout_text)
    for body in reversed(objects):
        if _looks_like_draft(body):
            continue
        repaired, normalizations = _repair_json_body(body)
        if repaired is None:
            continue
        try:
            return json.loads(repaired), "balanced_repair", tuple(normalizations or ())
        except json.JSONDecodeError:
            continue
    return None, None, ()


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


# social-post-v1 consumer contract: the model-facing fields the app requires.
# `hashtags` is NEVER a model-facing field; it is generated in Python afterwards.
_REQUIRED_FIELDS = ("hook", "caption", "cta", "content_angle", "intended_audience")


def _validate_contract(copy: dict | None) -> tuple[list[str], list[str]]:
    """Return (missing_fields, validation_errors) for the social-post-v1 contract."""
    missing: list[str] = []
    errors: list[str] = []
    if not isinstance(copy, dict):
        return list(_REQUIRED_FIELDS), ["payload is not a JSON object"]
    for field in _REQUIRED_FIELDS:
        value = copy.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    if not copy.get("caption"):
        errors.append("caption empty")
    return missing, errors


_GIT_PROVENANCE_CACHE: dict[str, object] | None = None


def _git_provenance() -> dict[str, object]:
    """(git_commit, git_dirty) for the repo this module lives in, cached per process.

    Shelling out to git on every request is slow and this changes at most once per
    deploy, so the result is computed once and reused for the process lifetime.
    """
    global _GIT_PROVENANCE_CACHE
    if _GIT_PROVENANCE_CACHE is not None:
        return _GIT_PROVENANCE_CACHE
    root = str(Path(__file__).resolve().parent.parent)
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=root, check=False,
        )
        git_commit = head.stdout.strip() or None
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=root, check=False,
        ).stdout.strip())
    except Exception:
        git_commit, dirty = None, False
    _GIT_PROVENANCE_CACHE = {"git_commit": git_commit, "git_dirty": dirty}
    return _GIT_PROVENANCE_CACHE


def runtime_provenance() -> dict:
    """Report what is actually imported/running, for runtime verification.

    Uses the imported module's own `__file__` (via sys.modules) so it reports the
    path that is genuinely loaded -- a wrong path here means a stale import, e.g.
    the app running from a different worktree than the one being edited. Safe to
    call from app.py (no Hermes invocation).
    """
    git = _git_provenance()
    # Import-and-report rather than returning None: promo_copy is always imported by
    # app.py, and reporting its real loaded path is the point of this endpoint.
    try:
        promo_copy_path = str(__import__("promo_copy").__file__)
    except Exception:
        promo_copy_path = None
    this_module = sys.modules.get(__name__)
    agent_post_writer_path = str(getattr(this_module, "__file__", "") or Path(__file__).resolve())
    hermes = _resolve_hermes()
    return {
        "git_commit": git.get("git_commit"),
        "git_dirty": git.get("git_dirty"),
        "promo_copy_path": promo_copy_path,
        "agent_post_writer_path": agent_post_writer_path,
        "agent_posts_enabled": bool(hermes),
        "prompt_contract_version": "social-post-v1",
        "hermes_path": hermes,
        "hermes_flags": "-Q --reasoning none",
        "reasoning": "none",
        "max_turns": 500,
        "pid": os.getpid(),
        "process_start_time": _process_start_time(),
        "cwd": str(Path.cwd()),
    }


def _process_start_time() -> str:
    try:
        import psutil  # type: ignore

        return str(psutil.Process(__import__("os").getpid()).create_time())
    except Exception:
        return ""


def generate_post_result(
    abbr: str,
    title: str,
    chapter: str,
    hook: str,
    material: dict | None = None,
    *,
    skills: str = _DEFAULT_SKILLS,
    timeout: int = 180,
    max_turns: int = 4,
) -> AgentPostResult:
    """Run Hermes and return a fully-structured AgentPostResult.

    Never raises — every failure path produces a terminal-status result so the
    caller can fall back to the template engine with precise diagnostics.
    """
    material = material or {}
    # Mint the run id ONCE, before any terminal return, so every outcome -- including
    # HERMES_NOT_ENABLED -- carries a stable identity and persists a lifecycle row.
    # The uuid4 suffix prevents a same-second PK collision silently UPSERTing over an
    # earlier run for the same novel/chapter.
    run_id = (
        f"agentpost_{abbr}_{chapter}_"
        f"{__import__('time').strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"
    )
    hermes = _resolve_hermes()
    if not hermes:
        _log("FAIL: hermes CLI not resolvable", abbr=abbr)
        # Not a bare early return: this terminal outcome persists a run row like
        # every other branch, so "received a result" implies "row exists".
        return _finalize(
            AgentPostResult(
                status=AgentPostStatus.HERMES_NOT_ENABLED,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                fallback_reason="hermes CLI not resolvable",
            ),
            run_id=run_id,
            abbr=abbr, novel=title, chapter=chapter,
            stdout_text="", stdout_raw=b"", stderr_text="", normalized=None,
            execution=None,
        )
    brief_path = _brief_for_abbr(abbr)
    brief_text = ""
    if brief_path and Path(brief_path).exists():
        try:
            brief_text = Path(brief_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            brief_text = ""
    prompt = _build_prompt(abbr, title, chapter, hook, brief_text, material)

    argv = [hermes, "chat", "-q", prompt, "-s", skills, "-Q", "--reasoning", "none",
            "--max-turns", str(max_turns)]
    # Strip the Hermes venv leak (broken numpy) + suppress banner/spinner.
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["HERMES_QUIET"] = "1"
    # Gate 3A Outcome A: --reasoning none yields a single clean JSON object
    # reliably. Keep max_turns generous (the skill needs vault reads).
    started_at = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
    t0 = __import__("time").time()
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=timeout,
            env=env,
            cwd=str(Path.cwd()),
        )
    except subprocess.TimeoutExpired as exc:
        completed_at = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
        duration_ms = int((__import__("time").time() - t0) * 1000)
        _log(f"FAIL: subprocess timeout: {exc!r}", abbr=abbr)
        return _finalize(
            AgentPostResult(
                status=AgentPostStatus.HERMES_TIMEOUT,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                fallback_reason="hermes subprocess timed out",
                execution=HermesExecution(
                    command_flags=tuple(argv), exit_code=None, duration_ms=duration_ms,
                    started_at=started_at, completed_at=completed_at, reasoning="none",
                    skills=skills, max_turns=str(max_turns),
                    stdout_replacement_count=0, error=repr(exc),
                ),
            ),
            run_id=run_id,
            abbr=abbr, novel=title, chapter=chapter,
            stdout_text="", stdout_raw=b"", stderr_text="", normalized=None,
            execution=HermesExecution(
                command_flags=tuple(argv), exit_code=None, duration_ms=duration_ms,
                started_at=started_at, completed_at=completed_at, reasoning="none",
                skills=skills, max_turns=str(max_turns),
                stdout_replacement_count=0, error=repr(exc),
            ),
        )
    except (OSError, ValueError) as exc:
        completed_at = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
        duration_ms = int((__import__("time").time() - t0) * 1000)
        _log(f"FAIL: subprocess error: {exc!r}", abbr=abbr)
        return _finalize(
            AgentPostResult(
                status=AgentPostStatus.HERMES_PROCESS_FAILED,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                fallback_reason=f"hermes subprocess error: {exc!r}",
                execution=HermesExecution(
                    command_flags=tuple(argv), exit_code=None, duration_ms=duration_ms,
                    started_at=started_at, completed_at=completed_at, reasoning="none",
                    skills=skills, max_turns=str(max_turns), error=repr(exc),
                ),
            ),
            run_id=run_id,
            abbr=abbr, novel=title, chapter=chapter,
            stdout_text="", stdout_raw=b"", stderr_text="", normalized=None,
            execution=HermesExecution(
                command_flags=tuple(argv), exit_code=None, duration_ms=duration_ms,
                started_at=started_at, completed_at=completed_at, reasoning="none",
                skills=skills, max_turns=str(max_turns), error=repr(exc),
            ),
        )
    completed_at = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
    duration_ms = int((__import__("time").time() - t0) * 1000)
    # Keep raw bytes; decode separately so exact bytes remain available for
    # provenance. Never concatenate stdout (candidate content) and stderr
    # (Hermes diagnostics / session_id line).
    stdout_raw = proc.stdout or b""
    stderr_raw = proc.stderr or b""
    stdout_text = stdout_raw.decode("utf-8", errors="replace")
    stderr_text = stderr_raw.decode("utf-8", errors="replace")
    # session_id: arrives on stderr (not stdout) in -Q mode; strip it there only.
    stderr_text = _strip_session_line(stderr_text)
    execution = HermesExecution(
        command_flags=tuple(argv), exit_code=proc.returncode, duration_ms=duration_ms,
        started_at=started_at, completed_at=completed_at, reasoning="none", skills=skills,
        max_turns=str(max_turns), stdout_replacement_count=stdout_text.count("\ufffd"),
    )
    if proc.returncode != 0:
        _log(
            f"FAIL: hermes rc={proc.returncode}",
            abbr=abbr,
            stdout=stdout_text[:2000],
            stderr=stderr_text[:2000],
        )
        return _finalize(
            AgentPostResult(
                status=AgentPostStatus.HERMES_PROCESS_FAILED,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                fallback_reason=f"hermes rc={proc.returncode}",
                execution=execution,
            ),
            run_id=run_id,
            abbr=abbr, novel=title, chapter=chapter,
            stdout_text=stdout_text, stdout_raw=stdout_raw,
            stderr_text=stderr_text, normalized=None, execution=execution,
        )
    if not stdout_text.strip():
        _log("FAIL: empty hermes stdout", abbr=abbr, stderr=stderr_text[:1500])
        return _finalize(
            AgentPostResult(
                status=AgentPostStatus.HERMES_EMPTY_OUTPUT,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                fallback_reason="hermes produced no output",
                execution=execution,
            ),
            run_id=run_id,
            abbr=abbr, novel=title, chapter=chapter,
            stdout_text=stdout_text, stdout_raw=stdout_raw,
            stderr_text=stderr_text, normalized=None, execution=execution,
        )
    data, parse_mode, parse_normalizations = _extract_json(stdout_text)
    # Normalize to the flat consumer contract. Accepts both the wrapped skill
    # output ({"variations":[...]}) and the legacy flat response. None => the
    # final block was not found / not parseable.
    normalized = _unwrap_variation(data)
    if normalized is None:
        # A JSON object WAS found but failed the unwrap (no caption / malformed
        # variations). Distinguish a found-but-invalid contract (envelope-only,
        # empty required fields) from a genuinely missing final block so the
        # caller records the precise missing_fields.
        if isinstance(data, dict):
            missing, validation_errors = _validate_contract(data)
            if missing or validation_errors:
                _log(
                    f"FAIL: contract validation failed missing={missing} errors={validation_errors}",
                    abbr=abbr,
                    stdout=stdout_text[:3000],
                    stderr=stderr_text[:1500],
                )
                return _finalize(
                    AgentPostResult(
                        status=AgentPostStatus.CONTRACT_VALIDATION_FAILED,
                        copy=None,
                        raw_response_path=None,
                        run_id=run_id,
                        parse_mode=parse_mode,
                        normalizations=parse_normalizations,
                        validation_errors=tuple(validation_errors),
                        missing_fields=tuple(missing),
                        fallback_reason=f"contract validation failed: missing={missing}",
                        execution=execution,
                    ),
                    run_id=run_id,
                    abbr=abbr, novel=title, chapter=chapter,
                    stdout_text=stdout_text, stdout_raw=stdout_raw,
                    stderr_text=stderr_text, normalized=None, execution=execution,
                )
        _log(
            "FAIL: output not parseable as post JSON (missing caption / empty or malformed variations)",
            abbr=abbr,
            stdout=stdout_text[:3000],
            stderr=stderr_text[:1500],
        )
        return _finalize(
            AgentPostResult(
                status=AgentPostStatus.FINAL_BLOCK_NOT_FOUND,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                parse_mode=parse_mode,
                normalizations=parse_normalizations,
                fallback_reason="reasoning transcript contained no complete final block",
                execution=execution,
            ),
            run_id=run_id,
            abbr=abbr, novel=title, chapter=chapter,
            stdout_text=stdout_text, stdout_raw=stdout_raw,
            stderr_text=stderr_text, normalized=None, execution=execution,
        )
    missing, validation_errors = _validate_contract(normalized)
    if missing or validation_errors:
        _log(
            f"FAIL: contract validation failed missing={missing} errors={validation_errors}",
            abbr=abbr,
            stdout=stdout_text[:3000],
            stderr=stderr_text[:1500],
        )
        return _finalize(
            AgentPostResult(
                status=AgentPostStatus.CONTRACT_VALIDATION_FAILED,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                parse_mode=parse_mode,
                normalizations=parse_normalizations,
                validation_errors=tuple(validation_errors),
                missing_fields=tuple(missing),
                fallback_reason=f"contract validation failed: missing={missing}",
                execution=execution,
            ),
            run_id=run_id,
            abbr=abbr, novel=title, chapter=chapter,
            stdout_text=stdout_text, stdout_raw=stdout_raw,
            stderr_text=stderr_text, normalized=None, execution=execution,
        )
    normalized["_source"] = "hermes_agent"
    return _finalize(
        AgentPostResult(
            status=AgentPostStatus.SUCCESS,
            copy=normalized,
            raw_response_path=None,
            run_id=run_id,
            parse_mode=parse_mode,
            normalizations=parse_normalizations,
            execution=execution,
        ),
        run_id=run_id,
        abbr=abbr, novel=title, chapter=chapter,
        stdout_text=stdout_text, stdout_raw=stdout_raw,
        stderr_text=stderr_text, normalized=normalized, execution=execution,
    )


def _finalize(
    result: AgentPostResult,
    *,
    run_id: str,
    abbr: str,
    novel: str,
    chapter: str,
    stdout_text: str,
    stdout_raw: bytes,
    stderr_text: str,
    normalized: dict | None,
    execution: HermesExecution | None,
) -> AgentPostResult:
    """Persist the run to SQLite (the lifecycle source of truth), then return.

    Failed runs are persisted too (most valuable diagnostics). A successful
    generation whose record fails to persist must NOT silently proceed: it is
    downgraded to DATABASE_PERSIST_FAILED and falls back to the template, with an
    emergency file log (never re-entering the unavailable DB).

    `run_id` is minted by the caller before the subprocess launch so it is stable
    across every terminal path and can be returned on the result.
    """
    try:
        import automation_db  # local import keeps the module boundary clean

        root = Path(__file__).resolve().parent.parent
        fields: list[tuple[int, str, str | None]] = []
        if isinstance(normalized, dict):
            for i, fld in enumerate(_REQUIRED_FIELDS):
                fields.append((i, fld, str(normalized.get(fld) or "") or None))
        automation_db.insert_agent_post_run(
            root,
            run_id=run_id,
            novel=novel,
            chapter=chapter,
            title=novel,
            status=result.status.value,
            fallback_reason=result.fallback_reason,
            provider=execution.resolved_provider if execution else None,
            model=execution.resolved_model if execution else None,
            command_flags=" ".join(execution.command_flags) if execution else None,
            request_text=None,
            decoded_stdout=stdout_text,
            raw_stdout=stdout_raw,
            stderr_text=stderr_text,
            selected_final_block=None,
            hook=normalized.get("hook") if normalized else None,
            caption=normalized.get("caption") if normalized else None,
            cta=normalized.get("cta") if normalized else None,
            content_angle=normalized.get("content_angle") if normalized else None,
            intended_audience=normalized.get("intended_audience") if normalized else None,
            parse_mode=result.parse_mode,
            validation_errors=",".join(result.validation_errors) or None,
            started_at=execution.started_at if execution else None,
            completed_at=execution.completed_at if execution else None,
            duration_ms=execution.duration_ms if execution else None,
            exit_code=execution.exit_code if execution else None,
        )
        automation_db.replace_agent_post_fields(root, run_id, fields)
    except Exception as exc:  # persistence failure: never silently proceed
        _log(f"FAIL: persistence error: {exc!r}", abbr=abbr)
        _emergency_log(abbr, novel, chapter, result, exc)
        if result.status is AgentPostStatus.SUCCESS:
            return AgentPostResult(
                status=AgentPostStatus.DATABASE_PERSIST_FAILED,
                copy=None,
                raw_response_path=None,
                run_id=run_id,
                parse_mode=result.parse_mode,
                normalizations=result.normalizations,
                fallback_reason=f"generation succeeded but persistence failed: {exc!r}",
                execution=execution,
            )
    return result


def _emergency_log(abbr: str, novel: str, chapter: str, result: AgentPostResult, exc: Exception) -> None:
    """Append-only emergency log when the SQLite lifecycle store is unavailable."""
    try:
        emerg = _LOG_PATH.parent / "agent_post_writer_emergency.log"
        line = (
            f"{__import__('time').strftime('%Y-%m-%dT%H:%M:%S')} "
            f"PERSIST_FAIL abbr={abbr} novel={novel} chapter={chapter} "
            f"status={result.status.value} reason={result.fallback_reason!r} error={exc!r}\n"
        )
        with emerg.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def agent_result_metadata(result: AgentPostResult) -> dict[str, object]:
    """Internal provenance metadata for a bundle, for BOTH success and failure.

    Always returns the same key set so downstream artifacts have a stable shape.
    Internal metadata only -- never public copy.

    `_agent_used` is deliberately provisional (False) here: this function cannot
    know whether the caller actually consumed the copy. Each call site overwrites
    it based on real downstream consumption. Do not derive it from `status`.
    """
    execution = result.execution
    return {
        "_agent_requested": True,
        "_agent_used": False,  # provisional; the call site sets the truth
        "_agent_status": result.status.value,
        "_agent_run_id": result.run_id,
        "_agent_source": "hermes_agent" if result.copy else None,
        "_agent_fallback_reason": result.fallback_reason,
        "_agent_model": execution.resolved_model if execution else "unknown",
        "_agent_provider": execution.resolved_provider if execution else "unknown",
        "_agent_reasoning": execution.reasoning if execution else "none",
        "_agent_parse_mode": result.parse_mode,
        "_agent_duration_ms": execution.duration_ms if execution else None,
        "_agent_schema_version": "social-post-v1",
    }


# Backward-compatible alias. Nothing in-repo imports this name any more; kept so an
# external caller does not break on the rename.
agent_fallback_metadata = agent_result_metadata


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
    """Backward-compatible thin wrapper: returns the copy dict, or None to fall back.

    Keeps the four existing app.py call sites unchanged during migration. Prefer
    `generate_post_result` for new code that needs diagnostics.
    """
    result = generate_post_result(
        abbr, title, chapter, hook, material,
        skills=skills, timeout=timeout, max_turns=max_turns,
    )
    return result.copy


if __name__ == "__main__":
    # Smoke test: python tools/agent_post_writer.py HA "Ch 24" "Kai's golden ember flares."
    _a = (sys.argv[1] if len(sys.argv) > 1 else "HA")
    _t = (sys.argv[2] if len(sys.argv) > 2 else "Ch 24")
    _h = (sys.argv[3] if len(sys.argv) > 3 else "")
    _res = generate_post_result(_a, _t, _t, _h, {})
    print(f"status={_res.status.value} missing={_res.missing_fields} reason={_res.fallback_reason}")
    print(json.dumps(_res.copy, indent=2, ensure_ascii=False) if _res.copy else "NULL (fallback)")
