"""Synthetic (non-manuscript) test of the production R21 beat-hash contract.
Production: tools.structured_location_authority_r21.sha256_text(text) = sha256(str(text).encode('utf-8'))
and tools.structured_scene_location_r21_wiring.chapter_beat_scope hashes str(beat).encode('utf-8').
Contract: exact bytes, NO normalization (whitespace, line endings, unicode form and case all matter)."""
import hashlib
import unicodedata

from tools import structured_location_authority_r21 as core
from tools import structured_scene_location_r21_wiring as w

S = "Synthetic test beat: the lantern hangs over the gate."


def ref(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_deterministic_and_matches_reference():
    assert core.sha256_text(S) == core.sha256_text(S) == ref(S)
    assert core.sha256_text("") == hashlib.sha256(b"").hexdigest()


def test_changed_text_changes_sha():
    assert core.sha256_text(S) != core.sha256_text(S.replace("lantern", "lanterns"))


def test_no_whitespace_or_line_ending_normalization():
    variants = [S, S + " ", " " + S, S + "\n", S.replace(" ", "  ", 1), S.replace(" ", "\t", 1),
                "a\nb", "a\r\nb", "a\rb"]
    shas = [core.sha256_text(v) for v in variants]
    assert len(set(shas)) == len(variants)
    assert all(core.sha256_text(v) == ref(v) for v in variants)


def test_no_unicode_or_case_normalization():
    nfc = unicodedata.normalize("NFC", "caf\u00e9 gate")
    nfd = unicodedata.normalize("NFD", "caf\u00e9 gate")
    assert nfc != nfd and core.sha256_text(nfc) != core.sha256_text(nfd)
    assert core.sha256_text(nfc) == ref(nfc)
    assert core.sha256_text(S) != core.sha256_text(S.upper())
    assert core.sha256_text("\u201cquote\u201d") != core.sha256_text('"quote"')


def test_non_str_is_coerced_with_str():
    assert core.sha256_text(123) == ref("123")


def test_wiring_scope_uses_same_contract(monkeypatch):
    monkeypatch.setenv(w.FLAG, "1")
    beats = [S, "a\r\nb", unicodedata.normalize("NFD", "caf\u00e9")]
    with w.chapter_beat_scope("HA", beats):
        assert w._SCOPE.get()["SHAS"] == [core.sha256_text(b) for b in beats]
    w._JOB.clear()
