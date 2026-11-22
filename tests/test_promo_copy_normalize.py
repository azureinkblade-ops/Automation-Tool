"""promo_copy.normalize_story_text sentence-gap rule (import normalizer), CPU only, never touches Docs.

The old rule re.sub(r"([.!?])([A-Z\"'])", r"\1 \2") detached closing quotes (`property."` -> `property. "`,
`Grip." He` -> `Grip. " He`) and split initials (`R.H.` -> `R. H.`). The fixed rule keeps both tight but still
splits real run-ons and spaces an opening quote that starts the next sentence. chapter_revision_hash keeps the
old rule so stored contentHash / royalRoadReviewedHash values stay valid.
"""
from __future__ import annotations

import hashlib
import re

import pytest

import promo_copy as P

n = P.normalize_story_text


def _old_rule(text: str) -> str:
    """The pre-fix pipeline for ASCII text (encoding repair / curly / dash steps are no-ops here)."""
    text = re.sub(r"([.!?])([A-Z\"'])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z][a-z])", r"\1 \2", text)
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize("src", [
    'Grip." He let go.',
    'She is not a property."',
    '"I lived in it." She did not look at him.',
    '"That\'s a forgery."',
    "'Run.' She ran.",
    'Why?" he asked.',
    'Stop!" Then silence.',
])
def test_closing_quote_stays_tight(src):
    assert n(src) == src


@pytest.mark.parametrize("src", ["R.H. Vale signed it.", "J.R.R. wrote it.", "Ask A.B. about it.", 'Signed, R.H."'])
def test_initials_stay_intact(src):
    assert n(src) == src


@pytest.mark.parametrize("src,want", [
    ("It ended.Next came the rain.", "It ended. Next came the rain."),
    ("Ask!Then go.", "Ask! Then go."),
    ("Why?Because.", "Why? Because."),
    ("A.B. said hi.Then left.", "A.B. said hi. Then left."),
    ('It ended."Next," he said.', 'It ended. "Next," he said.'),  # opening quote of the next sentence
    ("end.'Tis so.", "end. 'Tis so."),
])
def test_run_on_sentences_still_split(src, want):
    assert n(src) == want


def test_curly_quote_step_still_runs_and_closing_quote_stays_tight():
    # The curly-quote step maps \u201c/\u201d -> " and \u2018/\u2019 -> ' (before the gap rule), then the closing quote stays tight.
    assert n("\u201cGrip.\u201d He let go.") == '"Grip." He let go.'
    assert n("She is not a property.\u201d") == 'She is not a property."'
    assert n("\u2018Run.\u2019 She ran.") == "'Run.' She ran."
    assert n("It ended.\u201cNext,\u201d he said.") == 'It ended. "Next," he said.'
    assert n("A\u2014B \u2013 C") == "A-B - C"


def test_other_steps_unchanged():
    assert n("  a  \n b\tc ") == "a b c"
    assert n("someWhere") == "some Where"  # camel split rule untouched


SAMPLES = [
    'Grip." He let go. R.H. Vale.Then "Run," she said.\u201d And J.R.R. left.',
    'She is not a property." "I lived in it." She did not. end.Next Why?"No."',
]


@pytest.mark.parametrize("s", SAMPLES)
def test_word_counts_cannot_change(s):
    # chapter_word_counts counts re.findall(r"\w+"): a space next to . ! ? never changes the tokens.
    words = lambda t: re.findall(r"\w+", t)
    assert words(n(s)) == words(n(s, legacy_sentence_gap=True))


@pytest.mark.parametrize("s", SAMPLES + ['A."B', "R.H. Vale", 'x."'])
def test_revision_hash_normalization_is_the_old_rule(s):
    ascii_s = s.replace("\u201d", '"')
    assert P.normalize_story_text_for_revision_hash(ascii_s) == _old_rule(ascii_s)
    assert n(ascii_s, legacy_sentence_gap=True) == _old_rule(ascii_s)


def test_app_chapter_revision_hash_keeps_old_hashes():
    app = pytest.importorskip("app")
    s = 'She is not a property."\n\n"I lived in it." She did not. R.H. Vale.'
    assert app.chapter_revision_hash(s) == hashlib.sha256(_old_rule(s).encode("utf-8")).hexdigest()


def test_parse_manual_chapter_output_round_trips_quotes_and_initials():
    app = pytest.importorskip("app")
    body = ('"I lived in it." She did not look at him. R.H. Vale had signed the order."\n\n'
            '"That\'s a forgery."\n\n'
            "J.R.R. stood. Why?\" he asked. Stop!\" Then silence.")
    title, parsed = app.parse_manual_chapter_output("Chapter 7: The Wall\n\n" + body, "Chapter 7")
    assert title == "Chapter 7: The Wall"
    assert parsed == body