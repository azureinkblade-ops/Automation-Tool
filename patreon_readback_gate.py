"""PROPOSED (not applied): Patreon post-save read-back gate. Pure functions; stdlib only; no app import.

The Playwright helper (verifyPersistedPatreonPost) reloads the saved post and reports what Patreon actually persisted.
This gate re-checks that read-back in Python against values the helper never sees:
  * expected tier set derived from the job stage (inner_disciple -> Inner Disciple only; path_initiate -> Path Initiate only)
  * the SAVED chapter word count (chapter_word_counts.json: seeded from Product Performance's independent per-chapter count, then
    recorded by the import hook when a chapter is written to the Docs).  A missing / invalid saved count FAILS CLOSED.
  * chapter_split_v2 is only a SECONDARY DIAGNOSTIC: its count is reported next to the saved one, a disagreement is reported
    as a diagnostic, and it never turns a failing verdict into a pass or a passing one into a failure.
Any failure -> the job fails (it is never marked verified / ledger-complete).
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

TIER_BY_STAGE = {"inner_disciple": "Inner Disciple", "path_initiate": "Path Initiate"}
ALL_TIERS = ("Inner Disciple", "Path Initiate")
REQUIRED_CHECKS = ("canonicalPostUrl", "title", "body", "paidAccess", "tierAccess", "tiers", "date", "time", "media")
# Saved counts include the heading line. Calibration (544 chapters, unpatched app.docs_chapter_text vs seed): app chapter text = saved + 0..6;
# the Patreon body may drop the heading line (<= ~15 words).  See test_seed_file_calibration in test_patreon_readback_gate.py.
BODY_LOW_PCT, BODY_LOW_SLACK = 0.98, 25
BODY_HIGH_PCT, BODY_HIGH_SLACK = 1.02, 40
SPLITTER_DIAG_TOLERANCE = 8   # splitter drops a trailing next-title line (<= 7 words seen); more than that is a disagreement


def words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def body_bounds(saved_words: int) -> tuple[int, int]:
    return int(saved_words * BODY_LOW_PCT) - BODY_LOW_SLACK, int(saved_words * BODY_HIGH_PCT) + BODY_HIGH_SLACK


def splitter_chapter_words(full_text: str, number: int) -> int:
    """SECONDARY DIAGNOSTIC ONLY: whole-chapter words (heading included) from chapter_split_v2.  Imported lazily so a splitter
    problem can never break the gate itself."""
    import chapter_split_v2 as split
    ch = split.find_chapter(full_text, int(number))
    if ch is None:
        raise RuntimeError(f"chapter {number} not found by chapter_split_v2")
    return words(split.chapter_text(full_text, ch))


def valid_count(record: Any) -> Optional[int]:
    w = record.get("words") if isinstance(record, dict) else None
    return w if isinstance(w, int) and not isinstance(w, bool) and w > 0 else None


def evaluate_readback(row: Dict[str, Any], stage: str, count_record: Optional[Dict[str, Any]], splitter_words: Optional[int] = None,
                      splitter_error: str = "") -> Dict[str, Any]:
    reasons: List[str] = []
    diagnostics: List[str] = []
    submit = row.get("submitResult") if isinstance(row.get("submitResult"), dict) else {}
    pv = submit.get("persistedVerification") if isinstance(submit.get("persistedVerification"), dict) else {}
    checks = pv.get("checks") if isinstance(pv.get("checks"), dict) else {}
    rb = pv.get("readback") if isinstance(pv.get("readback"), dict) else {}
    if not submit.get("submitted"):
        reasons.append("post was not submitted")
    if not pv:
        reasons.append("no persisted read-back in helper result")
    for key in REQUIRED_CHECKS:
        if checks.get(key) is not True:
            reasons.append(f"read-back check '{key}' is not true")
    want = TIER_BY_STAGE.get(stage)
    if want is None:
        reasons.append(f"unknown stage '{stage}'")
    else:
        expected = {t: (t == want) for t in ALL_TIERS}
        states = rb.get("tierStates") if isinstance(rb.get("tierStates"), dict) else None
        if states is None:
            reasons.append("read-back has no tierStates (helper too old / selector failed)")
        elif {t: states.get(t) for t in ALL_TIERS} != expected:
            reasons.append(f"tier selection read back as {states}, expected {expected}")
    saved_count = valid_count(count_record)
    bw = rb.get("bodyWords")
    lo = hi = None
    if saved_count is None:
        reasons.append("no saved word count for this chapter (chapter_word_counts.json) - failing closed")
    else:
        lo, hi = body_bounds(saved_count)
        if not isinstance(bw, int) or isinstance(bw, bool):
            reasons.append("read-back has no bodyWords")
        elif not (lo <= bw <= hi):
            reasons.append(f"saved body is {bw} words; saved chapter count is {saved_count} (accepted {lo}..{hi})")
    if splitter_error:
        diagnostics.append(f"splitter diagnostic unavailable: {splitter_error}")
    elif splitter_words is not None and saved_count is not None:
        if abs(saved_count - splitter_words) > SPLITTER_DIAG_TOLERANCE:
            diagnostics.append(f"chapter_split_v2 counts {splitter_words} words but the saved count is {saved_count} - splitter or saved count is wrong, check before trusting either")
    return {"ok": not reasons, "reasons": reasons, "diagnostics": diagnostics, "savedChapterWords": saved_count,
            "savedBodyWords": bw if isinstance(bw, int) and not isinstance(bw, bool) else None,
            "splitterWords": splitter_words, "accepted": [lo, hi] if lo is not None else None, "stage": stage}