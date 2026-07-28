"""Slice 2 AIVSB retrieval consumer wiring — tests.

Verifies the OFF-path contract (flag OFF -> identical result, no retrieval call,
no DB read, no logging) and the ON-path behavior (bounded injection, provenance
capture, zero-hit + exception fallbacks, cross-novel isolation, deterministic
formatting). Consumer-only; does not test retrieval ranking/embedding/indexing.

Run:
  PYTHONPATH=. python -m pytest tests/aivsb/test_slice2_wiring.py -q
"""
from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path
import tempfile
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _flag_off():
    # Ensure the flag is OFF for every test unless a test explicitly sets it.
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"
    importlib.reload(__import__("promo_copy", fromlist=["x"]))
    yield
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"


def _controlled_inputs():
    # hp novel: used by non-seeding tests (faked hits / OFF-path). No index match needed.
    material = {
        "abbr": "hp",
        "novel": "Hundredfold Path",
        "chapter": "21",
        "title": "Chapter 21: The First Stirring",
        "phrases": ["A quiet duel of technique.", "Power costs more than gold."],
        "characters": ["Kael"],
    }
    return material


def _controlled_inputs_en():
    # Matches the seeded fixture (style_guides/en.yaml -> novel_id "en").
    material = {
        "abbr": "en",
        "novel": "Eternal Nexus",
        "chapter": "21",
        "title": "Chapter 21: The First Stirring",
        "phrases": ["A quiet duel of technique.", "Power costs more than gold."],
        "characters": ["Kael"],
    }
    return material


def _deterministic_stubs():
    def rot(key, n):
        return 0
    def ledger(abbr, chapter):
        return {"last_chapter": 20, "rotation_index": 0}
    def relstatus(story, chapter, material):
        return {"is_live": False}
    return rot, ledger, relstatus


def test_flag_off_identical_and_no_retrieval_call():
    import promo_copy
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs()

    call_count = {"retrieve": 0, "get_run": 0}

    def fake_retrieve(*a, **k):
        call_count["retrieve"] += 1
        raise AssertionError("retrieve must not be called when flag is OFF")
    def fake_run(*a, **k):
        call_count["get_run"] += 1
        raise AssertionError("get_active_index_run must not be called when flag is OFF")

    with mock.patch("scripts.aivsb.retrieval.retrieve", side_effect=fake_retrieve), \
         mock.patch("scripts.aivsb.retrieval.get_active_index_run", side_effect=fake_run):
        base = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )
        again = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )
    # Exact structural equality (deep) and serialization equality.
    assert base == again
    import json
    assert json.dumps(base, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert call_count["retrieve"] == 0
    assert call_count["get_run"] == 0
    # Sanity: the block is absent in both.
    assert "[AIVSB RETRIEVED CONTEXT]" not in base["caption"]
    assert "[AIVSB RETRIEVED CONTEXT]" not in base["facebook_post"]
    assert "[AIVSB RETRIEVED CONTEXT]" not in base["x_post"]


def _seed_index(root):
    """Build a small index + a COMPLETED run using the provenance lane."""
    import automation_db as adb
    from scripts.aivsb.retrieval import provenance as P, chunk_extractor as CE
    adb.init_db(root)
    src = Path("C:/Users/David/Documents/Inkblade Author Studio/scripts/aivsb")
    tree = root / "src"
    (tree / "style_guides").mkdir(parents=True)
    (tree / "characters").mkdir(parents=True)
    import shutil
    shutil.copy(src / "style_guides" / "en.yaml", tree / "style_guides" / "en.yaml")
    shutil.copy(src / "characters" / "kael.yaml", tree / "characters" / "kael.yaml")
    chunks = list(CE.extract_from_path(tree / "style_guides" / "en.yaml", tree))
    chunks += list(CE.extract_from_path(tree / "characters" / "kael.yaml", tree))
    P._git = lambda *a, cwd: "abc123" if a == ("rev-parse", "HEAD") else ""
    rid = P.run_index(root, tree, chunks, embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    return rid, len(chunks)


def _connect_to(tmp_db_path):
    """Return a real connection to the seeded temp DB (used to redirect adb.connect)."""
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_flag_on_injects_bounded_context_and_captures_provenance():
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(__import__("promo_copy", fromlist=["x"]))
    import promo_copy
    import automation_db as adb
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()

    tmp = Path(tempfile.mkdtemp())
    rid, n = _seed_index(tmp)
    tmp_db = tmp / "automation_state.db"
    eval_records = []
    with mock.patch.object(adb, "connect", lambda root: _connect_to(tmp_db)):
        out = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
            retrieval_eval_sink=eval_records.append,
        )
    assert "[AIVSB RETRIEVED CONTEXT]" in out["caption"]
    assert "[END AIVSB RETRIEVED CONTEXT]" in out["caption"]
    hits_in_block = out["caption"].count("- (")
    assert hits_in_block <= 5
    assert len(eval_records) == 1
    rec = eval_records[0]
    assert rec["retrieval_enabled"] is True
    assert rec["retrieval_used"] is True
    assert rec["run_id"] == rid
    assert rec["manifest_hash"]
    assert rec["fallback_reason"] is None


def test_flag_on_zero_hits_preserves_original_prompt():
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(__import__("promo_copy", fromlist=["x"]))
    import promo_copy
    import automation_db as adb
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()

    tmp = Path(tempfile.mkdtemp())
    rid, n = _seed_index(tmp)
    tmp_db = tmp / "automation_state.db"
    with mock.patch.object(adb, "connect", lambda root: _connect_to(tmp_db)), \
         mock.patch("scripts.aivsb.retrieval.retrieve", return_value=[]):
        os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"
        importlib.reload(__import__("promo_copy", fromlist=["x"]))
        base = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )
        os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
        importlib.reload(__import__("promo_copy", fromlist=["x"]))
        eval_records = []
        out = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
            retrieval_eval_sink=eval_records.append,
        )
    assert "[AIVSB RETRIEVED CONTEXT]" not in out["caption"]
    assert out["caption"] == base["caption"]
    assert eval_records and eval_records[0]["retrieval_used"] is False
    assert eval_records[0]["fallback_reason"] == "no_hits"


def test_flag_on_retrieval_exception_preserves_original_prompt():
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(__import__("promo_copy", fromlist=["x"]))
    import promo_copy
    import automation_db as adb
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()

    tmp = Path(tempfile.mkdtemp())
    rid, n = _seed_index(tmp)
    tmp_db = tmp / "automation_state.db"
    with mock.patch.object(adb, "connect", lambda root: _connect_to(tmp_db)), \
         mock.patch("scripts.aivsb.retrieval.retrieve", side_effect=RuntimeError("boom")):
        os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"
        importlib.reload(__import__("promo_copy", fromlist=["x"]))
        base = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )
        os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
        importlib.reload(__import__("promo_copy", fromlist=["x"]))
        eval_records = []
        out = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
            retrieval_eval_sink=eval_records.append,
        )
    assert "[AIVSB RETRIEVED CONTEXT]" not in out["caption"]
    assert out["caption"] == base["caption"]
    assert eval_records and eval_records[0]["retrieval_used"] is False
    assert eval_records[0]["fallback_reason"].startswith("retrieval_error:")


def test_cross_novel_isolation_in_injected_context():
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(__import__("promo_copy", fromlist=["x"]))
    import promo_copy
    import automation_db as adb
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs()  # abbr=hp

    class _Hit:
        def __init__(self, cid, nov, dom, prov):
            self.chunk_id = cid; self.novel_id = nov; self.domain = dom
            self.score = 1.0; self.summary = f"body-{cid}"; self.provenance = prov
    faked = [
        _Hit("hp::a", "hp", "visual_identity", {"source_file": "x"}),
        _Hit("en::b", "en", "visual_identity", {"source_file": "y"}),
        _Hit("hp::c", "hp", "visual_identity", {"source_file": "z"}),
    ]
    tmp = Path(tempfile.mkdtemp())
    tmp_db = tmp / "automation_state.db"
    with mock.patch.object(adb, "connect", lambda root: _connect_to(tmp_db)), \
         mock.patch("scripts.aivsb.retrieval.retrieve", return_value=faked), \
         mock.patch("scripts.aivsb.retrieval.get_active_index_run", return_value=None):
        out = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )
    block = out["caption"]
    assert "body-en::b" not in block
    assert "body-hp::a" in block
    assert "body-hp::c" in block


def test_context_formatting_deterministic():
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(__import__("promo_copy", fromlist=["x"]))
    import promo_copy
    import automation_db as adb
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs()

    class _Hit:
        def __init__(self, cid, nov, dom, prov):
            self.chunk_id = cid; self.novel_id = nov; self.domain = dom
            self.score = 1.0; self.summary = f"body-{cid}"; self.provenance = prov
    faked = [
        _Hit("hp::z", "hp", "visual_identity", {"source_file": "a"}),
        _Hit("hp::a", "hp", "visual_identity", {"source_file": "b"}),
        _Hit("hp::a", "hp", "visual_identity", {"source_file": "b"}),  # duplicate
        _Hit("hp::m", "hp", "visual_identity", {"source_file": "c"}),
    ]
    tmp = Path(tempfile.mkdtemp())
    tmp_db = tmp / "automation_state.db"
    with mock.patch.object(adb, "connect", lambda root: _connect_to(tmp_db)), \
         mock.patch("scripts.aivsb.retrieval.retrieve", return_value=faked), \
         mock.patch("scripts.aivsb.retrieval.get_active_index_run", return_value=None):
        out1 = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )
        out2 = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )
    b1 = out1["caption"]
    b2 = out2["caption"]
    assert b1 == b2
    assert b1.count("body-hp::a") == 1
    assert b1.index("body-hp::a") < b1.index("body-hp::m") < b1.index("body-hp::z")
