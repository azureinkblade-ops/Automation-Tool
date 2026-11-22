"""Publish bodies keep closing quotes and initials tight (CPU only, no Docs, no posting).

format_chapter_for_platform (Patreon patreon.txt, Royal Road royal-road.txt, live-release check) and
normalize_story_body_text (YouTube story-hook script) had their own copies of the old
re.sub(r"([.!?])...") rule that re-added `Grip. " He` / `R. H.` at publish time. Both now use
promo_copy.space_sentence_gaps. docs_chapter_payload keeps the old rule on purpose: its "text" feeds
chapter_revision_hash, pack source hashes and word counts, which must stay byte-stable.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

import promo_copy as P

app = pytest.importorskip("app")

RAW = (
    "Chapter 9: The Wall\n\n"
    '"Hold the line," she said. He kept his Grip." He let go.\n\n'
    "R.H. Vale signed it. J.R.R. stood by.Then the bell rang.\n\n"
    '"Ressa Hask."\n\n'
    'She is not a property."'
)


def _old_gap(text: str) -> str:
    return re.sub(r"([.!?])(?=[A-Z\u201c\u2018\"'])", r"\1 ", text)


def _publish(include_post_note=False):
    return app.format_chapter_for_platform("Chapter 9: The Wall", RAW, 9, "EN", include_post_note=include_post_note)


def test_royal_road_body_keeps_closing_quote_and_initials_tight():
    body = app.royal_road_editor_spacing(_publish())
    assert 'Grip." He let go.' in body
    assert "R.H. Vale" in body and "J.R.R. stood" in body
    assert '"Ressa Hask."' in body and 'She is not a property."' in body
    assert not re.search(r'[.!?] ["\x27](?=\s|$)', body)  # no detached closing quote anywhere
    assert "by. Then the bell" in body  # real run-on still split


def test_patreon_body_with_post_note_keeps_them_tight():
    body = _publish(include_post_note=True)
    assert 'Grip." He let go.' in body and "R.H. Vale" in body and 'property."' in body


def test_publish_body_words_unchanged_vs_old_rule():
    words = lambda t: re.findall(r"\w+", t)
    old = app.format_chapter_for_platform("Chapter 9: The Wall", RAW, 9, "EN", include_post_note=False, legacy_sentence_gap=True)
    assert words(old) == words(_publish())


def test_docs_payload_text_stays_on_the_old_rule_so_hashes_do_not_move():
    payload = app.docs_chapter_payload("EN", 9, "Chapter 9: The Wall", "Chapter 9: The Wall", RAW)
    legacy = app.format_chapter_for_platform("Chapter 9: The Wall", RAW, 9, "EN", include_post_note=False,
                                             legacy_sentence_gap=True).strip()
    assert payload["text"] == legacy
    assert "R. H." in payload["text"] or "R.H." in payload["text"]
    assert payload["word_count"] == len(re.findall(r"\w+", legacy))
    assert app.chapter_revision_hash(payload["text"]) == hashlib.sha256(
        P.normalize_story_text_for_revision_hash(legacy).encode("utf-8")).hexdigest()


def test_legacy_flag_is_exactly_the_old_formatter_rule():
    s = 'a.B c."D e.\u201cF g!\'H i?J'
    assert P.space_sentence_gaps(s.replace("\u201c", '"'), legacy=True) == _old_gap(s.replace("\u201c", '"'))


def test_story_hook_body_normalizer_keeps_them_tight():
    out = app.normalize_story_body_text('He kept his Grip." He let go. R.H. Vale.Then "Run," she said.')
    assert out == 'He kept his Grip." He let go. R.H. Vale. Then "Run," she said.'


def test_no_other_copy_of_the_old_rule_left_in_app_py():
    src = Path(app.__file__).read_text(encoding="utf-8")
    hits = [m.start() for m in re.finditer(r're\.sub\(r"\(\[\.!\?\]\)', src)]
    lines = [src.count("\n", 0, h) + 1 for h in hits]
    assert len(lines) == 1, lines  # only the legacy branch in format_chapter_for_platform
    legacy_line = src.splitlines()[lines[0] - 2]
    assert "Pre-2026-11-21 rule" in legacy_line