import random

from tools.chapter_overlap_gate import check_chapter, check_workflow_state, is_truncated, main, overlap_ratio

VOCAB = [f"w{i}" for i in range(3000)]


def make_text(seed, n_words=800):
    rng = random.Random(seed)
    words = [rng.choice(VOCAB) for _ in range(n_words)]
    sents = [" ".join(words[i:i + 12]).capitalize() + "." for i in range(0, n_words, 12)]
    return " ".join(sents)


def test_distinct_chapters_pass():
    r = check_chapter(make_text(1), make_text(2))
    assert r.passed, r.reasons
    assert r.overlap_ratio == 0.0
    assert r.identical_sentence_count == 0


def test_heavy_overlap_fails():
    prev = make_text(3)
    cur = prev + " " + make_text(4, 300)
    r = check_chapter(cur, prev)
    assert not r.passed
    assert any(x.startswith("overlap_with_previous:") for x in r.reasons)
    assert r.overlap_ratio > 0.5
    assert r.identical_sentence_count > 10


def test_short_shared_run_below_min_run_ignored():
    prev = make_text(5)
    shared = " ".join(prev.split()[:30])
    cur = make_text(6) + " " + shared + "."
    assert check_chapter(cur, prev).overlap_ratio == 0.0


def test_overlap_ratio_exact():
    prev = [f"p{i}" for i in range(100)]
    cur = prev[:50] + [f"c{i}" for i in range(50)]
    assert overlap_ratio(cur, prev, 40) == 0.5


def test_normalization_case_punct():
    prev = make_text(7)
    cur = prev.upper().replace(".", "!")
    assert check_chapter(cur, prev).overlap_ratio > 0.95


def test_truncation():
    t = make_text(8)
    r = check_chapter(t.rstrip(".") + " and then he", make_text(9))
    assert not r.passed and "truncated_mid_sentence" in r.reasons
    for ok in ['end."', "end.\u201d", "end\u2026", "end?", "end!)  \n"]:
        assert not is_truncated(ok)


def test_stub():
    r = check_chapter("Short chapter here.", make_text(10))
    assert "stub_too_short:3" in r.reasons and not r.passed


def test_fail_closed_empty():
    for t in (None, "", "   \n"):
        r = check_chapter(t, make_text(11))
        assert not r.passed and r.reasons == ["empty_or_missing_text"]


def test_missing_previous_fails_closed():
    r = check_chapter(make_text(12), None)
    assert not r.passed and "previous_text_missing" in r.reasons


def test_cli(tmp_path, capsys):
    a, b, c = tmp_path / "a.txt", tmp_path / "b.txt", tmp_path / "c.txt"
    a.write_text(make_text(13), encoding="utf-8")
    b.write_text(make_text(14), encoding="utf-8")
    c.write_text(make_text(13), encoding="utf-8")
    assert main([str(a), str(b)]) == 0
    assert main([str(a), str(c)]) == 1
    assert main([str(a), str(tmp_path / "missing.txt")]) == 1
    assert main([]) == 2


def test_complete_without_text():
    for t in (None, "", " \n\t"):
        r = check_chapter(t, make_text(15), marked_complete=True)
        assert not r.passed and "complete_without_text" in r.reasons
    assert "complete_without_text" not in check_chapter("", "x").reasons


def test_workflow_state_helper(tmp_path):
    import json
    bad, good, inc = tmp_path / "b.json", tmp_path / "g.json", tmp_path / "i.json"
    bad.write_text(json.dumps({"chapterNumber": 1, "complete": True, "chapterText": "  "}))
    good.write_text(json.dumps({"complete": True, "chapterText": "Text."}))
    inc.write_text(json.dumps({"complete": False, "chapterText": ""}))
    assert check_workflow_state(str(bad))["reasons"] == ["complete_without_text"]
    assert check_workflow_state(str(good))["passed"]
    assert check_workflow_state(str(inc))["passed"]
    assert not check_workflow_state(str(tmp_path / "nope.json"))["passed"]
