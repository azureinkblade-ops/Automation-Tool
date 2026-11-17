"""PROPOSED (not applied): safer Docs chapter splitter.  Pure functions, no app import.

Rule (Product Performance scan 2026-11-17, output/pp-chapter-split-scan-20261117/scan3.json):
  * A "Chapter N ..." occurrence is a heading only if it is at paragraph start OR directly after
    sentence-ending punctuation (EN docs run headings into the previous paragraph: '...together.Chapter 77: Title').
    Mid-sentence references ('...from Chapter 107 echo in memory') never count.
  * Number must be > last heading and <= last+3 (first heading of the file is always accepted).
  * Same number with a sub-part label (12B, 42b, '25 Part 2') after chapter 12/42/25 is a CONTINUATION of that chapter.
  * A repeat of the same heading ends the chapter; the duplicate copy is dropped until the next valid heading.
    Exception: if the chapter so far is a stub (< STUB_WORDS words, e.g. HA-66 'Chapter 66' / 'Edit') the repeat restarts the chapter.
  * A trailing bare line that is only the next chapter's title is dropped from the previous chapter.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

HEADING_RE = re.compile(r"\bChapter\s+(?P<label>\d+[A-Za-z]?(?:\s+Part\s+\d+)?)\b(?P<tail>[^\n]{0,120})", re.IGNORECASE)
SENTENCE_END = set(".!?\u2026\"'\u201d\u2019)]*_")
MAX_JUMP = 3
STUB_WORDS = 50


@dataclass
class Chapter:
    number: int
    label: str
    start: int            # offset of the heading in full_text
    end: int              # exclusive; text[start:end] is the chapter incl. heading
    duplicates_dropped: int = 0
    sub_parts: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    end_heading: str = ""   # heading text that ended this chapter (next chapter or repeated duplicate)


def _num(label: str) -> int:
    return int(re.search(r"\d+", label).group(0))


def _has_suffix(label: str) -> bool:
    return bool(re.search(r"\d[A-Za-z]|\bPart\b", label, re.IGNORECASE))


def heading_is_anchored(text: str, pos: int) -> bool:
    """True when the heading is at text/paragraph start or right after sentence-ending punctuation."""
    j = pos - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] == "\n":
        return True
    return text[j] in SENTENCE_END


def _words(s: str) -> int:
    return len(re.findall(r"\w+", s))


def split_chapters(full_text: str) -> List[Chapter]:
    chapters: List[Chapter] = []
    cur: Optional[Chapter] = None
    skipping = False  # inside a dropped duplicate copy
    for m in HEADING_RE.finditer(full_text):
        if not heading_is_anchored(full_text, m.start()):
            continue
        label = re.sub(r"\s+", " ", m.group("label").strip())
        n = _num(label)
        last_n = cur.number if cur else None
        if cur is None:
            cur = Chapter(n, label, m.start(), len(full_text)); chapters.append(cur); continue
        if skipping:
            if last_n < n <= last_n + MAX_JUMP:
                skipping = False
                cur = Chapter(n, label, m.start(), len(full_text)); chapters.append(cur)
            continue
        if n == last_n:
            same = label.lower() == cur.label.lower() or (label.lower() in {s.lower() for s in cur.sub_parts})
            if not same and _has_suffix(label):
                cur.sub_parts.append(label)            # sub-part heading: continuation
                continue
            body_words = _words(full_text[cur.start:m.start()]) - _words(cur.label) - 1
            if body_words < STUB_WORDS:                # stub before the real chapter: restart
                chapters.pop(); cur = Chapter(n, label, m.start(), len(full_text)); chapters.append(cur)
                cur.notes.append("restarted after stub")
                continue
            cur.end = m.start(); cur.end_heading = m.group(0); cur.duplicates_dropped += 1; skipping = True
            continue
        if last_n < n <= last_n + MAX_JUMP:
            cur.end = m.start(); cur.end_heading = m.group(0)
            cur = Chapter(n, label, m.start(), len(full_text)); chapters.append(cur)
        # else: out-of-sequence reference -> ignore
    return chapters


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s).strip().lower()


def _is_bare_title_line(line: str, end_heading: str) -> bool:
    """Short unpunctuated last line that merely repeats the title of the heading that ends the chapter."""
    s = line.strip()
    if not s or len(s.split()) > 14 or re.search(r"[.!?\u201d\"\u2019']$", s):
        return False
    nl, nh = _norm(s), _norm(end_heading)
    return bool(nl) and nl in nh


def chapter_text(full_text: str, ch: Chapter) -> str:
    """Chapter text incl. heading; a trailing bare next-title line is dropped."""
    paras = full_text[ch.start:ch.end].rstrip().split("\n\n")
    if len(paras) > 2 and ch.end_heading and _is_bare_title_line(paras[-1], ch.end_heading):
        paras = paras[:-1]
    return "\n\n".join(paras).strip()


def find_chapter(full_text: str, number: int, chapters: Optional[List[Chapter]] = None) -> Optional[Chapter]:
    for ch in (chapters if chapters is not None else split_chapters(full_text)):
        if ch.number == number:
            return ch
    return None