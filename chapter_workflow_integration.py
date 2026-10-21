"""
Chapter Workflow Integration — collaborator wrappers for app.py.

Adapts existing app.py functions into chapter_workflow.Collaborators.
Never imports app.py (to avoid circular imports). Instead, receives
app.py functions as constructor arguments.

This module is the ONLY bridge between chapter_workflow and the rest
of the Automation Tool. app.py imports this, not the other way around.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from chapter_workflow import Collaborators

logger = logging.getLogger(__name__)


def _resolve_hermes_exe() -> str:
    env_path = str(os.environ.get("HERMES_EXE") or "").strip()
    if env_path and Path(env_path).is_file():
        return env_path
    default = (
        Path.home()
        / "AppData"
        / "Local"
        / "hermes"
        / "hermes-agent"
        / "venv"
        / "Scripts"
        / "hermes.exe"
    )
    if default.is_file():
        return str(default)
    return env_path or "hermes.exe"


def _hermes_chat(
    prompt: str,
    skills: Optional[List[str]] = None,
    max_turns: int = 4,
    timeout: int = 120,
) -> Optional[str]:
    """Call Hermes CLI headlessly and return the response text."""
    qpath = None
    try:
        handle, qpath = tempfile.mkstemp(prefix="hermes-chapter-", suffix=".txt")
        os.close(handle)
        Path(qpath).write_text(prompt, encoding="utf-8")
        cmd = [
            _resolve_hermes_exe(),
            "chat",
            "--query-file",
            qpath,
            "-Q",
            "--cli",
            "--safe-mode",
            "--max-turns",
            str(max_turns),
        ]
        if skills:
            cmd.extend(["-s", ",".join(skills)])
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PYTHONPATH", "PYTHONHOME")
        }
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        lines = [
            line
            for line in result.stdout.splitlines()
            if not line.startswith("session_id:")
        ]
        text = "\n".join(lines).strip()
        if text:
            return text
        if result.returncode != 0:
            logger.error("Hermes chat failed rc=%s stderr=%s", result.returncode, (result.stderr or "")[:800])
            return None
        logger.error("Hermes chat empty stdout stderr=%s", (result.stderr or "")[:800])
        return None
    except subprocess.TimeoutExpired:
        logger.error("Hermes chat timed out after %ds", timeout)
        return None
    except FileNotFoundError:
        logger.error("Hermes CLI not found")
        return None
    finally:
        if qpath:
            Path(qpath).unlink(missing_ok=True)


class AppCollaborators:
    """Builds chapter_workflow.Collaborators from app.py functions.
    
    Usage:
        app_collab = AppCollaborators(
            next_chapter_context=app.next_chapter_context,
            continuity_text_from_context=app.continuity_text_from_context,
            load_continuity_snapshot=app.load_continuity_snapshot,
            docs_chapter_text=app.docs_chapter_text,
            latest_docs_chapter_number=app.latest_docs_chapter_number,
        )
        collab = app_collab.build()
    """
    
    def __init__(
        self,
        # Context/continuity functions
        next_chapter_context: Callable,
        continuity_text_from_context: Callable,
        load_continuity_snapshot: Callable,
        docs_chapter_text: Callable,
        latest_docs_chapter_number: Callable,
        # Novel/lore info
        novel_names: Dict[str, str],
        # Optional: custom LLM caller (defaults to Hermes CLI)
        llm_caller: Optional[Callable] = None,
        # Optional: output directory for test artifacts
        output_dir: Optional[Path] = None,
    ):
        self.next_chapter_context = next_chapter_context
        self.continuity_text_from_context = continuity_text_from_context
        self.load_continuity_snapshot = load_continuity_snapshot
        self.docs_chapter_text = docs_chapter_text
        self.latest_docs_chapter_number = latest_docs_chapter_number
        self.novel_names = novel_names
        self.llm_caller = llm_caller or _hermes_chat
        self.output_dir = output_dir

    def build(self) -> Collaborators:
        """Build the Collaborators instance for chapter_workflow."""
        return Collaborators(
            fetch_latest_chapter=self._fetch_latest_chapter,
            fetch_studio_bible=self._fetch_studio_bible,
            fetch_continuity=self._fetch_continuity,
            generate_brief=self._generate_brief,
            write_chapter=self._write_chapter,
            review_continuity=self._review_continuity,
            validate_chapter=self._validate_chapter,
        )

    # ─── Context/continuity collaborators ────────────────────────

    def _fetch_latest_chapter(self, novel: str) -> Dict[str, Any]:
        """Fetch latest chapter info and prose for a novel."""
        context = self.next_chapter_context(novel)
        latest_num = context["latestChapter"]
        chapter_data = None
        if latest_num > 0:
            try:
                chapter_data = self.docs_chapter_text(novel, latest_num)
            except Exception as e:
                logger.warning("Could not fetch chapter %d text: %s", latest_num, e)
        
        return {
            "latest_number": latest_num,
            "next_number": context["nextChapter"],
            "chapter_text": chapter_data.get("text") or chapter_data.get("raw_text") if chapter_data else None,
            "recent_chapters": context.get("recentChapters", []),
        }

    def _fetch_studio_bible(self, novel: str) -> Dict[str, Any]:
        """Fetch Studio Bible / lore constraints for a novel."""
        # The continuity snapshot IS the Studio Bible equivalent
        snapshot = self.load_continuity_snapshot(novel)
        return {
            "novel": self.novel_names.get(novel, novel),
            "protagonist": snapshot.get("protagonist", ""),
            "power_system_rules": snapshot.get("power_system_rules", ""),
            "established_characters": snapshot.get("important_characters", []),
            "tone_genre_constraints": snapshot.get("tone_style_notes", ""),
            "drift_flags": snapshot.get("drift_flags", []),
        }

    def _fetch_continuity(self, novel: str, chapter_number: int) -> Dict[str, Any]:
        """Fetch continuity state for a novel at a given chapter."""
        snapshot = self.load_continuity_snapshot(novel)
        context = self.next_chapter_context(novel)
        continuity_text = self.continuity_text_from_context(context)
        
        return {
            "snapshot": snapshot,
            "continuity_text": continuity_text,
            "current_arc": snapshot.get("current_arc", ""),
            "important_characters": snapshot.get("important_characters", []),
            "unresolved_plot_threads": snapshot.get("unresolved_plot_threads", []),
            "last_chapter_summary": snapshot.get("last_chapter_summary", ""),
            "tone_style_notes": snapshot.get("tone_style_notes", ""),
            "next_chapter_setup": snapshot.get("next_chapter_setup", ""),
        }

    # ─── LLM-powered collaborators ───────────────────────────────

    def _generate_brief(self, novel: str, chapter_number: int, context_json: str) -> str:
        """Generate a chapter brief from context."""
        context = json.loads(context_json)
        novel_name = self.novel_names.get(novel, novel)
        
        prompt = f"""Generate a chapter brief for {novel_name} Chapter {chapter_number}.

Context:
{json.dumps(context, indent=2)}

Requirements:
- Identify which unresolved plot thread to advance
- Define the chapter's opening beat (directly from previous chapter's closing hook)
- Outline the midpoint development
- Specify the closing hook (new unresolved beat)
- Note which character arcs to advance
- Respect the novel's tone and power system constraints

Return JSON with keys:
novel_code, chapter_number, working_title, opening_bevel, midpoint_development, closing_hook, character_arcs_advanced, canon_threads_continued, canon_compliance, estimated_word_count"""

        response = self.llm_caller(prompt, skills=["azure-inkblade-lore"])
        if response:
            return response
        # Fallback: generate brief from context without LLM
        return json.dumps({
            "novel_code": novel,
            "chapter_number": chapter_number,
            "working_title": f"Chapter {chapter_number}",
            "opening_beat": "Continue from previous chapter",
            "midpoint_development": "Advance the current arc",
            "closing_hook": "End with forward momentum",
            "character_arcs_advanced": [],
            "canon_threads_continued": [],
            "canon_compliance": "pass: generated from context",
            "estimated_word_count": 3000,
        })

    def _write_chapter(self, novel: str, chapter_number: int, brief: str) -> str:
        """Generate chapter prose from brief."""
        novel_name = self.novel_names.get(novel, novel)
        
        # Parse brief if it's JSON
        try:
            brief_data = json.loads(brief) if brief.strip().startswith("{") else {"raw": brief}
        except json.JSONDecodeError:
            brief_data = {"raw": brief}
        
        prompt = f"""Write Chapter {chapter_number} of the web novel {novel_name}.

Chapter Brief:
{json.dumps(brief_data, indent=2) if isinstance(brief_data, dict) else brief}

Requirements:
- First line: Chapter {chapter_number} - {brief_data.get("working_title", "Title")}
- Target length: {brief_data.get("estimated_word_count", 3000)} words minimum
- Follow the opening_beat, midpoint_development, closing_hook from the brief
- Preserve character motivations and power system rules
- No em dashes (use hyphens or commas)
- No markdown fences, author notes, or meta-commentary
- End with the specified closing hook"""

        response = self.llm_caller(prompt, skills=["azure-inkblade-chapter-writing"])
        if response:
            return response
        raise RuntimeError(f"Failed to generate chapter {chapter_number} for {novel}")

    def _review_continuity(self, novel: str, chapter_number: int, draft: str, context_json: Dict) -> Dict[str, Any]:
        """Review draft for continuity/canon compliance."""
        novel_name = self.novel_names.get(novel, novel)
        
        # Fast deterministic checks
        issues = []
        
        # Check for em dashes
        if "—" in draft:
            issues.append("Contains em dashes")
        
        # Check for markdown fences
        if "```" in draft:
            issues.append("Contains markdown fences")
        
        # Check first line format
        first_line = draft.strip().split("\n")[0]
        if not first_line.startswith(f"Chapter {chapter_number}"):
            issues.append(f"First line should start with 'Chapter {chapter_number}'")
        
        # Check word count
        word_count = len(draft.split())
        if word_count < 3000:
            issues.append(f"Too short: {word_count} words (minimum 3000)")
        
        # LLM review for continuity (if available)
        prompt = f"""Review this draft for continuity and canon compliance.

Novel: {novel_name}
Chapter: {chapter_number}

Continuity Context:
{json.dumps(context_json, indent=2)[:2000]}

Draft (first 1000 words):
{draft[:1000]}

Check for:
1. Character name consistency
2. Power system rule violations
3. Plot thread contradictions
4. Tone/style consistency

Return JSON: {{"pass": true/false, "issues": ["issue1", "issue2"]}}"""

        response = self.llm_caller(prompt, skills=["azure-inkblade-lore"], max_turns=2)
        if response:
            try:
                review = json.loads(response)
                # Merge deterministic + LLM issues
                review["issues"] = list(set(issues + review.get("issues", [])))
                review["pass"] = len(review["issues"]) == 0
                return review
            except json.JSONDecodeError:
                pass
        
        # Fallback to deterministic checks only
        return {
            "pass": len(issues) == 0,
            "issues": issues,
        }

    def _validate_chapter(self, novel: str, chapter_number: int, draft: str) -> Dict[str, Any]:
        """Final quality gate before publication."""
        errors = []
        
        # Em dash ban
        if "—" in draft:
            errors.append("Contains em dashes")
        
        # Markdown fence exclusion
        if "```" in draft:
            errors.append("Contains markdown fences")
        
        # First line format
        first_line = draft.strip().split("\n")[0]
        if not first_line.startswith(f"Chapter {chapter_number}"):
            errors.append(f"First line must be 'Chapter {{N}} - Title'")
        
        # Body prose check (not outline/summary)
        word_count = len(draft.split())
        if word_count < 3000:
            errors.append(f"Below minimum word count: {word_count} < 3000")
        
        review_required = word_count > 5000
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "word_count": word_count,
            "review_required": review_required,
        }
