"""Slice 2R AIVSB retrieval injection-boundary remediation — tests.

Verifies the recorded Slice 2R contract:
- NO retrieval text/IDs/query/delimiters reach the public result (canary + structural).
- OFF-path byte/structure identity; rotation state advances identically in both arms.
- Retrieved KnowledgeChunk.domain selects a curated caption_style via retrieval order
  (selected rank MAY exceed 1); unmapped domains are skipped; unknown domains degrade.
- Provenance distinguishes retrieval fallback (fallback_reason) from signal-consumption
  fallback (signal_fallback_reason); injected_chunk_ids stays [].

Run:
  PYTHONPATH=. python -m pytest tests/aivsb/test_slice2r_injection_boundary.py -q
"""
from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _flag_off():
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"
    importlib.reload(__import__("promo_copy", fromlist=["x"]))
    yield
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"


def _controlled_inputs_en():
    return {
        "abbr": "en",
        "novel": "Eternal Nexus",
        "chapter": "21",
        "title": "Chapter 21: The First Stirring",
        "phrases": ["A quiet duel of technique.", "Power costs more than gold."],
        "characters": ["Kael"],
    }


def _deterministic_stubs():
    def rot(key, n):
        return 0
    def ledger(abbr, chapter):
        return {"last_chapter": 20, "rotation_index": 0}
    def relstatus(story, chapter, material=None):
        return {"is_live": False}
    return rot, ledger, relstatus


CANARIES = ["PRIVATE_CANON_CANARY_7F31A9", "PRIVATE_SOURCE_PATH_CANARY_84D2", "PRIVATE_QUERY_CANARY_19C0"]
FROZEN_PUBLIC_KEYS = {
    "caption", "patreon_note", "facebook_post", "x_post", "x_thread_links",
    "post_focus", "caption_style", "tracking_campaign", "_agent_source",
}


def _seed_index(root):
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


@pytest.fixture
def seed_tmp_db(tmp_path):
    """Return the disposable SQLite file used by provenance lookup in ON tests."""
    import automation_db as adb

    _seed_index(tmp_path)
    return adb.db_path(tmp_path)


def _connect_to(tmp_db_path):
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _hit(chunk_id, domain, novel_id, summary, provenance=None):
    from scripts.aivsb.retrieval import RetrievalHit
    return RetrievalHit(
        chunk_id=chunk_id,
        novel_id=novel_id,
        domain=domain,
        score=1.0,
        summary=summary,
        provenance=provenance or {},
    )


def _on_harness(hits_in_order, seed_tmp_db):
    """Run build_platform_posts with flag ON, retrieval mocked, DB redirected to seed."""
    import promo_copy
    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(promo_copy)

    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()
    records = []
    rot_calls = {"count": 0, "args": None}

    def fake_retrieve(root, query, novel_id=None, top_n=5):
        if isinstance(hits_in_order, BaseException):
            raise hits_in_order
        return list(hits_in_order)

    orig_rotating = promo_copy.rotating_caption_style

    def spy_rotating(*a, **k):
        rot_calls["count"] += 1
        rot_calls["args"] = (a, k)
        return orig_rotating(*a, **k)

    with mock.patch("scripts.aivsb.retrieval.retrieve", side_effect=fake_retrieve), \
         mock.patch.object(promo_copy, "rotating_caption_style", side_effect=spy_rotating), \
         mock.patch("automation_db.connect", side_effect=lambda *a, **k: _connect_to(seed_tmp_db)):
        out = promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
            retrieval_eval_sink=records.append,
        )
    return out, records, rot_calls


def _off_result():
    import promo_copy

    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"
    importlib.reload(promo_copy)
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()
    return promo_copy.build_platform_posts(
        material["title"], material["chapter"], material,
        rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
    )


def _assert_no_leak(out):
    blob = " ".join(str(v) for v in out.values())
    import json
    blob += " " + json.dumps(out, sort_keys=True)
    for c in CANARIES:
        assert c not in blob, f"canary {c} leaked into public result"
    assert "[AIVSB RETRIEVED CONTEXT]" not in blob
    assert "[END AIVSB RETRIEVED CONTEXT]" not in blob
    assert set(out) == FROZEN_PUBLIC_KEYS
    for forbidden_key in {
        "run_id", "manifest_hash", "query", "returned_chunk_ids",
        "injected_chunk_ids", "derived_signal", "derived_signal_source_ids",
        "derived_signal_source_rank", "derived_signal_source_domain",
        "fallback_reason", "signal_fallback_reason",
    }:
        assert forbidden_key not in blob


def test_off_path_identity_and_no_retrieval_call():
    import promo_copy
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()
    calls = {"retrieve": 0, "run": 0}

    def fake_retrieve(*a, **k):
        calls["retrieve"] += 1
        raise AssertionError("retrieve must not run when flag OFF")
    def fake_run(*a, **k):
        calls["run"] += 1
        raise AssertionError("get_active_index_run must not run when flag OFF")

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
    assert base == again
    assert calls["retrieve"] == 0 and calls["run"] == 0
    _assert_no_leak(base)


def test_rank_preservation_uses_first_mappable_hit_without_chunk_id_resort(seed_tmp_db):
    hits = [
        _hit("z-rank-1", "worldbuilding", "en", CANARIES[0],
             {"source_file": CANARIES[1]}),
        _hit("a-rank-2", "character", "en", "safe summary"),
    ]

    out, records, rot_calls = _on_harness(hits, seed_tmp_db)

    assert out["caption_style"] == "worldbuilding"
    assert rot_calls["count"] == 1
    assert len(records) == 1
    record = records[0]
    assert record["returned_chunk_ids"] == ["z-rank-1", "a-rank-2"]
    assert record["injected_chunk_ids"] == []
    assert record["derived_signal"] == "worldbuilding"
    assert record["derived_signal_source_ids"] == ["z-rank-1"]
    assert record["derived_signal_source_rank"] == 1
    assert record["derived_signal_source_domain"] == "worldbuilding"
    assert record["fallback_reason"] is None
    assert record["signal_fallback_reason"] is None
    _assert_no_leak(out)


def test_unmapped_rank_one_is_skipped_and_rank_two_signal_is_recorded(seed_tmp_db):
    hits = [
        _hit("video-rank-1", "video", "en", CANARIES[0]),
        _hit("character-rank-2", "character", "en", "safe summary"),
    ]

    out, records, _ = _on_harness(hits, seed_tmp_db)

    assert out["caption_style"] == "character_moment"
    record = records[0]
    assert record["returned_chunk_ids"] == ["video-rank-1", "character-rank-2"]
    assert record["injected_chunk_ids"] == []
    assert record["derived_signal"] == "character_moment"
    assert record["derived_signal_source_ids"] == ["character-rank-2"]
    assert record["derived_signal_source_rank"] == 2
    assert record["derived_signal_source_domain"] == "character"
    assert record["signal_fallback_reason"] is None
    _assert_no_leak(out)


def test_hits_without_mappable_domain_preserve_baseline_and_record_signal_fallback(seed_tmp_db):
    hits = [
        _hit("video-rank-1", "video", "en", CANARIES[0]),
        _hit("future-rank-2", "future_domain", "en", CANARIES[1]),
    ]

    out, records, rot_calls = _on_harness(hits, seed_tmp_db)

    assert out["caption_style"] == "scene_hook"
    assert rot_calls["count"] == 1
    record = records[0]
    assert record["returned_chunk_ids"] == ["video-rank-1", "future-rank-2"]
    assert record["injected_chunk_ids"] == []
    assert record["fallback_reason"] is None
    assert record["derived_signal"] is None
    assert record["derived_signal_source_ids"] == []
    assert record["derived_signal_source_rank"] is None
    assert record["derived_signal_source_domain"] is None
    assert record["signal_fallback_reason"] == "no_mappable_domain"
    _assert_no_leak(out)


def test_zero_hits_equal_off_output_and_record_retrieval_fallback(seed_tmp_db):
    off = _off_result()

    out, records, rot_calls = _on_harness([], seed_tmp_db)

    assert out == off
    assert rot_calls["count"] == 1
    record = records[0]
    assert record["returned_chunk_ids"] == []
    assert record["injected_chunk_ids"] == []
    assert record["fallback_reason"] == "no_hits"
    assert record["signal_fallback_reason"] is None
    assert record["derived_signal"] is None
    assert record["derived_signal_source_ids"] == []
    assert record["derived_signal_source_rank"] is None
    assert record["derived_signal_source_domain"] is None
    _assert_no_leak(out)


def test_retrieval_exception_equal_off_output_and_record_normalized_failure(seed_tmp_db):
    off = _off_result()

    out, records, rot_calls = _on_harness(TimeoutError(CANARIES[0]), seed_tmp_db)

    assert out == off
    assert rot_calls["count"] == 1
    record = records[0]
    assert record["returned_chunk_ids"] == []
    assert record["injected_chunk_ids"] == []
    assert record["fallback_reason"] == "retrieval_error:TimeoutError"
    assert record["signal_fallback_reason"] is None
    assert record["derived_signal"] is None
    assert record["derived_signal_source_ids"] == []
    assert record["derived_signal_source_rank"] is None
    assert record["derived_signal_source_domain"] is None
    assert CANARIES[0] not in str(record)
    _assert_no_leak(out)


def test_rotation_call_is_identical_in_off_and_on_arms(seed_tmp_db):
    import promo_copy

    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()

    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "false"
    importlib.reload(promo_copy)
    with mock.patch.object(promo_copy, "rotating_caption_style", return_value="scene_hook") as off_spy:
        promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )

    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(promo_copy)
    hits = [_hit("character-rank-1", "character", "en", "safe summary")]
    with mock.patch("scripts.aivsb.retrieval.retrieve", return_value=hits), \
         mock.patch("automation_db.connect", side_effect=lambda *a, **k: _connect_to(seed_tmp_db)), \
         mock.patch.object(promo_copy, "rotating_caption_style", return_value="scene_hook") as on_spy:
        promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )

    assert off_spy.call_count == 1
    assert on_spy.call_count == 1
    assert off_spy.call_args == on_spy.call_args


def test_consumer_uses_repository_root_for_provenance_and_retrieval():
    import promo_copy

    os.environ["ENABLE_AIVSB_RETRIEVAL"] = "true"
    importlib.reload(promo_copy)
    rot, ledger, rel = _deterministic_stubs()
    material = _controlled_inputs_en()
    seen = {"run_root": None, "retrieve_root": None}

    def fake_run(root):
        seen["run_root"] = Path(root)
        return mock.Mock(run_id="run-1", manifest_hash="manifest-1")

    def fake_retrieve(root, query, novel_id=None, top_n=5):
        seen["retrieve_root"] = Path(root)
        return []

    with mock.patch("scripts.aivsb.retrieval.get_active_index_run", side_effect=fake_run), \
         mock.patch("scripts.aivsb.retrieval.retrieve", side_effect=fake_retrieve):
        promo_copy.build_platform_posts(
            material["title"], material["chapter"], material,
            rotation_next=rot, chapter_ledger_entry=ledger, release_status_for_chapter=rel,
        )

    assert seen["run_root"] == REPO_ROOT
    assert seen["retrieve_root"] == REPO_ROOT
