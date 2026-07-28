"""Slice 2 AIVSB retrieval consumer wiring — tests.

Verifies the OFF-path contract (flag OFF -> identical result, no retrieval call,
no DB read, no logging) and the ON-path behavior (bounded structured signal,
sink-only provenance, zero-hit + exception fallbacks, cross-novel isolation).
Consumer-only; does not test retrieval ranking/embedding/indexing.

Run:
  PYTHONPATH=. python -m pytest tests/aivsb/test_slice2_wiring.py -q
"""
from __future__ import annotations

import importlib
import json
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


def test_flag_on_keeps_public_output_clean_and_captures_signal_provenance():
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
    public_blob = json.dumps(out, sort_keys=True)
    assert "[AIVSB RETRIEVED CONTEXT]" not in public_blob
    assert "[END AIVSB RETRIEVED CONTEXT]" not in public_blob
    assert len(eval_records) == 1
    rec = eval_records[0]
    assert rec["retrieval_enabled"] is True
    assert rec["retrieval_used"] is True
    assert rec["run_id"] == rid
    assert rec["manifest_hash"]
    assert rec["fallback_reason"] is None
    assert rec["injected_chunk_ids"] == []
    for chunk_id in rec["returned_chunk_ids"]:
        assert chunk_id not in public_blob
    if rec["derived_signal"] is None:
        assert rec["derived_signal_source_ids"] == []
        assert rec["derived_signal_source_rank"] is None
        assert rec["derived_signal_source_domain"] is None
        assert rec["signal_fallback_reason"] == "no_mappable_domain"
    else:
        assert rec["derived_signal"] in {"character_moment", "worldbuilding"}
        assert len(rec["derived_signal_source_ids"]) == 1
        assert rec["derived_signal_source_rank"] >= 1
        assert rec["derived_signal_source_domain"] in {"character", "worldbuilding", "location"}
        assert rec["signal_fallback_reason"] is None


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


def test_cross_novel_isolation_in_derived_signal_and_public_output():
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
        _Hit("hp::a", "hp", "character", {"source_file": "x"}),
        _Hit("en::b", "en", "worldbuilding", {"source_file": "y"}),
        _Hit("hp::c", "hp", "location", {"source_file": "z"}),
    ]
    tmp = Path(tempfile.mkdtemp())
    tmp_db = tmp / "automation_state.db"
    eval_records = []
    with mock.patch.object(adb, "connect", lambda root: _connect_to(tmp_db)), \
         mock.patch("scripts.aivsb.retrieval.retrieve", return_value=faked), \
         mock.patch("scripts.aivsb.retrieval.get_active_index_run", return_value=None):
        out = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
            retrieval_eval_sink=eval_records.append,
        )
    public_blob = json.dumps(out, sort_keys=True)
    for hit in faked:
        assert hit.summary not in public_blob
        assert hit.chunk_id not in public_blob
    rec = eval_records[0]
    assert rec["returned_chunk_ids"] == ["hp::a", "en::b", "hp::c"]
    assert rec["injected_chunk_ids"] == []
    assert rec["derived_signal"] == "character_moment"
    assert rec["derived_signal_source_ids"] == ["hp::a"]
    assert rec["derived_signal_source_rank"] == 1
    assert rec["derived_signal_source_domain"] == "character"


def test_signal_selection_preserves_retrieval_order_deterministically():
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
        _Hit("hp::z", "hp", "video", {"source_file": "a"}),
        _Hit("hp::a", "hp", "character", {"source_file": "b"}),
        _Hit("hp::a", "hp", "character", {"source_file": "b"}),  # duplicate returned ID
        _Hit("hp::m", "hp", "location", {"source_file": "c"}),
    ]
    tmp = Path(tempfile.mkdtemp())
    tmp_db = tmp / "automation_state.db"
    eval_records = []
    with mock.patch.object(adb, "connect", lambda root: _connect_to(tmp_db)), \
         mock.patch("scripts.aivsb.retrieval.retrieve", return_value=faked), \
         mock.patch("scripts.aivsb.retrieval.get_active_index_run", return_value=None):
        out1 = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
            retrieval_eval_sink=eval_records.append,
        )
        out2 = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
            retrieval_eval_sink=eval_records.append,
        )
    assert out1 == out2
    assert len(eval_records) == 2
    expected_order = ["hp::z", "hp::a", "hp::a", "hp::m"]
    for rec in eval_records:
        assert rec["returned_chunk_ids"] == expected_order
        assert rec["injected_chunk_ids"] == []
        assert rec["derived_signal"] == "character_moment"
        assert rec["derived_signal_source_ids"] == ["hp::a"]
        assert rec["derived_signal_source_rank"] == 2
        assert rec["derived_signal_source_domain"] == "character"
    public_blob = json.dumps(out1, sort_keys=True)
    for hit in faked:
        assert hit.summary not in public_blob
        assert hit.chunk_id not in public_blob
