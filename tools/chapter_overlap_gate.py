"""Standalone chapter-quality gate (additive; not wired into any runner).

Detects heavy verbatim overlap with the previous chapter, mid-sentence
truncation, and stub-length chapters. Fails closed on empty/missing text.

CLI: python -m tools.chapter_overlap_gate <chapter.txt> <previous.txt>
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?\u2026])[\"'\u201d\u2019)\]]*\s+")
TERMINAL_CHARS = set(".!?\"'\u201d\u2019\u2026)]*~\u300d\u300f")


@dataclass
class ChapterCheckResult:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    overlap_ratio: float = 0.0
    identical_sentence_count: int = 0
    word_count: int = 0
    truncated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_words(text: str) -> List[str]:
    t = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    return _WORD_RE.findall(t)


def _sentences(text: str) -> List[str]:
    out = []
    for s in _SENT_SPLIT_RE.split(text):
        words = _normalize_words(s)
        if len(words) >= 6:
            out.append(" ".join(words))
    return out


def overlap_ratio(words: List[str], prev_words: List[str], min_run_words: int = 40) -> float:
    """Fraction of `words` covered by runs of >= min_run_words consecutive
    words that also appear consecutively in `prev_words`."""
    n = len(words)
    if n == 0 or len(prev_words) < min_run_words or n < min_run_words:
        return 0.0
    k = min_run_words
    prev_shingles = {tuple(prev_words[i:i + k]) for i in range(len(prev_words) - k + 1)}
    covered = [False] * n
    for i in range(n - k + 1):
        if tuple(words[i:i + k]) in prev_shingles:
            for j in range(i, i + k):
                covered[j] = True
    return sum(covered) / n


def is_truncated(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return True
    return stripped[-1] not in TERMINAL_CHARS


def check_chapter(
    text: Optional[str],
    previous_text: Optional[str],
    *,
    min_run_words: int = 40,
    max_overlap_ratio: float = 0.15,
    min_words: int = 500,
    marked_complete: bool = False,
) -> ChapterCheckResult:
    if text is None or not str(text).strip():
        reasons = ["empty_or_missing_text"]
        if marked_complete:
            reasons.append("complete_without_text")
        return ChapterCheckResult(passed=False, reasons=reasons, truncated=True)
    words = _normalize_words(text)
    reasons: List[str] = []
    ratio = 0.0
    identical = 0
    if previous_text is None or not str(previous_text).strip():
        reasons.append("previous_text_missing")
    else:
        prev_words = _normalize_words(previous_text)
        ratio = overlap_ratio(words, prev_words, min_run_words)
        prev_sents = set(_sentences(previous_text))
        identical = sum(1 for s in _sentences(text) if s in prev_sents)
        if ratio > max_overlap_ratio:
            reasons.append(f"overlap_with_previous:{ratio:.3f}")
    truncated = is_truncated(text)
    if truncated:
        reasons.append("truncated_mid_sentence")
    if len(words) < min_words:
        reasons.append(f"stub_too_short:{len(words)}")
    return ChapterCheckResult(
        passed=not reasons,
        reasons=reasons,
        overlap_ratio=round(ratio, 4),
        identical_sentence_count=identical,
        word_count=len(words),
        truncated=truncated,
    )


def check_workflow_state(path: str) -> dict:
    """Read-only: report a chapter-workflow-state JSON marked complete whose
    chapterText is empty/whitespace (reason complete_without_text)."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            state = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"path": path, "passed": False, "reasons": [f"state_unreadable:{type(exc).__name__}"]}
    complete = bool(state.get("complete"))
    text = state.get("chapterText")
    reasons = []
    if complete and (not isinstance(text, str) or not text.strip()):
        reasons.append("complete_without_text")
    return {"path": path, "chapterNumber": state.get("chapterNumber"),
            "complete": complete, "passed": not reasons, "reasons": reasons}


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: python -m tools.chapter_overlap_gate <chapter> <previous>", file=sys.stderr)
        return 2
    res = check_chapter(_read(argv[0]), _read(argv[1]))
    print(json.dumps(res.to_dict(), indent=2))
    return 0 if res.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
