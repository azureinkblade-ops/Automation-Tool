r"""PROPOSED (not applied): saved per-chapter word counts, the ground truth for the Patreon read-back gate.

File: chapter_word_counts.json (copy to the repo root next to app.py; override with env CHAPTER_WORD_COUNTS_FILE).
  {"schema": 1, "counting": "...", "chapters": {"HA-110": {"novel": "HA", "chapter": 110, "words": 9255,
     "source": "pp-true_word_counts", "docsCommit": "b3896115", "recordedAt": "...", "splitterWords": 9248}, ...}}

`words` = len(re.findall(r"\w+", whole chapter text INCLUDING the heading line))  (Product Performance's definition).
Sources: "pp-true_word_counts" (seed, independent marker-chain count), "import" (recorded by append_chapter_to_github_docs
at the moment a new chapter is written to the Docs; counted from the text actually uploaded), "manual".
Nothing here knows about the splitter: `splitterWords` is only a stored diagnostic.
Pure stdlib; atomic write (temp file + os.replace) under a process lock.
"""
from __future__ import annotations
import json, os, re, tempfile, threading, time
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = 1
COUNTING = r"words = len(re.findall(r'\w+', whole chapter text including the heading line))"
DEFAULT_PATH = Path(__file__).resolve().parent / "chapter_word_counts.json"
_LOCK = threading.Lock()
_CHAPTER_IN_TITLE = re.compile(r"\bChapter\s+(\d+)\b", re.IGNORECASE)


def words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def store_path(path: Optional[Path] = None) -> Path:
    return Path(path or os.environ.get("CHAPTER_WORD_COUNTS_FILE") or DEFAULT_PATH)


def key(abbr: str, chapter: int) -> str:
    return f"{str(abbr).upper().strip()}-{int(chapter)}"


def load(path: Optional[Path] = None) -> Dict[str, Any]:
    p = store_path(path)
    if not p.exists():
        return {"schema": SCHEMA, "counting": COUNTING, "chapters": {}}
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("chapters"), dict):
        raise ValueError(f"{p} is not a chapter word count file")
    return data


def get(abbr: str, chapter: int, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The saved record, or None when missing/unreadable/invalid (callers must fail closed on None)."""
    try:
        rec = load(path)["chapters"].get(key(abbr, chapter))
    except Exception:
        return None
    if not isinstance(rec, dict) or isinstance(rec.get("words"), bool) or not isinstance(rec.get("words"), int) or rec["words"] <= 0:
        return None
    return rec


def _write(data: Dict[str, Any], p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=True, sort_keys=True)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def record(abbr: str, chapter: int, word_count: int, source: str, docs_commit: str = "", path: Optional[Path] = None, **extra: Any) -> Dict[str, Any]:
    """Add/replace one chapter. A replaced, different count keeps the old value under `previous` (rewrites stay auditable)."""
    if isinstance(word_count, bool) or not isinstance(word_count, int) or word_count <= 0:
        raise ValueError(f"invalid word count {word_count!r}")
    p = store_path(path)
    with _LOCK:
        data = load(p)
        data["schema"], data["counting"] = SCHEMA, COUNTING
        k = key(abbr, chapter)
        rec: Dict[str, Any] = {"novel": str(abbr).upper().strip(), "chapter": int(chapter), "words": int(word_count), "source": source,
                               "docsCommit": docs_commit, "recordedAt": time.strftime("%Y-%m-%d %H:%M:%S")}
        rec.update({k2: v for k2, v in extra.items() if v is not None})
        old = data["chapters"].get(k)
        if isinstance(old, dict) and old.get("words") != rec["words"]:
            rec["previous"] = (old.get("previous") or []) + [{"words": old.get("words"), "source": old.get("source"), "docsCommit": old.get("docsCommit"), "recordedAt": old.get("recordedAt")}]
        data["chapters"][k] = rec
        _write(data, p)
    return rec


def commit_from_upload(upload_result: Any) -> str:
    """Best-effort commit sha from a GitHub contents-API style upload result ('' when not present)."""
    if isinstance(upload_result, dict):
        c = upload_result.get("commit")
        if isinstance(c, dict) and c.get("sha"):
            return str(c["sha"])[:40]
        if isinstance(upload_result.get("commitSha"), str):
            return upload_result["commitSha"][:40]
    return ""


def record_import(abbr: str, title: str, chapter_text: str, upload_result: Any = None, path: Optional[Path] = None) -> Dict[str, Any]:
    """Import hook: called right after the chapter reached the Docs. Counts the text that was actually uploaded
    (title/heading + body). Raises if the chapter number can't be read from the title; the caller must not fail the import on that
    (the gate fails closed on a missing count instead)."""
    m = _CHAPTER_IN_TITLE.search(title or "")
    if not m:
        raise ValueError(f"cannot read a chapter number from title {title!r}")
    n = int(m.group(1))
    rec = record(abbr, n, words(title) + words(chapter_text), "import", commit_from_upload(upload_result), path)
    return {"ok": True, "key": key(abbr, n), "words": rec["words"], "source": "import"}