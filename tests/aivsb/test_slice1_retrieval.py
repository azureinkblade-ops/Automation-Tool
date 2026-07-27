"""Slice 1 retrieval test suite.

Validates the extraction + storage + retrieval contract against the verified
17-file AIVSB corpus. The embedding model is optional; tests pass with or without
it (retrieve() degrades to metadata+keyword fallback). No corpus is copied; the
external AIVSB_SOURCE_PATH is read read-only.

Run:
  AIVSB_SOURCE_PATH="C:/Users/David/Documents/Inkblade Author Studio/scripts/aivsb" \
    PYTHONPATH=. python -m pytest tests/aivsb/test_slice1_retrieval.py -q
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
import tempfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = os.environ.get("AIVSB_SOURCE_PATH", "")

requires_source = pytest.mark.skipif(
    not SRC or not Path(SRC).exists(),
    reason="AIVSB_SOURCE_PATH not set / missing (required external canonical source)",
)


@requires_source
def test_extract_count_and_parse():
    from scripts.aivsb.retrieval.chunk_extractor import extract, ALLOWED_RELATIVE_PATHS
    src = Path(SRC)
    chunks = list(extract(src))
    assert len(chunks) > 0, "no chunks extracted"
    for c in chunks:
        assert c.chunk_id and c.novel_id and c.domain and c.content_hash
        assert c.body.strip()


@requires_source
def test_allowlist_only_no_recursive_scan():
    from scripts.aivsb.retrieval.chunk_extractor import iter_allowed_files, ALLOWED_RELATIVE_PATHS
    src = Path(SRC)
    files = list(iter_allowed_files(src))
    assert len(files) <= len(ALLOWED_RELATIVE_PATHS)
    for f in files:
        rel = str(f.relative_to(src)).replace("\\", "/")
        assert rel in ALLOWED_RELATIVE_PATHS
    assert not any(".model-acquisition" in str(f) for f in files)


@requires_source
def test_stable_ids_list_and_mapping_rooted():
    from scripts.aivsb.retrieval.chunk_extractor import extract_from_path
    src = Path(SRC)
    sf = extract_from_path(src / "characters" / "sf_protagonists.yaml", src)
    assert len(sf) >= 1
    assert all(c.chunk_id.startswith("characters/sf_protagonists.yaml::") for c in sf)
    en = extract_from_path(src / "style_guides" / "en.yaml", src)
    assert len(en) >= 1
    assert "::" in en[0].chunk_id


@requires_source
def test_cross_novel_leakage_and_metadata_filter(tmp_path):
    from scripts.aivsb.retrieval.chunk_extractor import extract
    from scripts.aivsb.retrieval.index_store import upsert_chunks
    from scripts.aivsb.retrieval.retriever import retrieve

    chunks = list(extract(Path(SRC)))
    upsert_chunks(tmp_path, chunks)

    leaks = retrieve(tmp_path, "emotionally intense VR awakening scene", novel_id="hp")
    for h in leaks:
        assert h.novel_id == "hp"
    assert len(leaks) >= 1

    hits = retrieve(tmp_path, "palette and lighting for Hundredfold Path",
                    novel_id="hp", domain="visual_identity")
    assert len(hits) >= 1
    for h in hits:
        assert h.novel_id == "hp"


@requires_source
def test_foreign_key_cascade_and_insert_guard(tmp_path):
    """Blocker 3: verify SQLite FK enforcement + cascade delete actually work."""
    from scripts.aivsb.retrieval.index_store import (
        upsert_chunks, upsert_embedding, delete_chunk, count_embeddings,
    )
    from scripts.aivsb.retrieval.chunk_extractor import extract
    from scripts.aivsb.retrieval.embed_worker import SHIPPING_MODEL

    chunks = list(extract(Path(SRC)))
    upsert_chunks(tmp_path, chunks)

    # (a) embedding cannot be inserted for an absent chunk
    conn = __import__("automation_db", fromlist=["connect"]).connect(tmp_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO chunk_embeddings (chunk_id, embedding_model, embedding_dim, "
                "embedded_at, content_hash, vector) VALUES (?,?,?,?,?,?)",
                ("nonexistent::chunk", SHIPPING_MODEL, 384, "now", "x", b"\x00" * 16),
            )
        conn.rollback()
    finally:
        conn.close()

    # (b) inserting a valid embedding, then deleting its chunk cascades the embedding
    some = chunks[0]
    upsert_embedding(tmp_path, some.chunk_id, SHIPPING_MODEL, None, 384, b"\x00" * 16, some.content_hash)
    assert count_embeddings(tmp_path) >= 1
    delete_chunk(tmp_path, some.chunk_id)
    assert count_embeddings(tmp_path) == 0, "embedding should be cascade-deleted with its chunk"


@requires_source
def test_stale_record_rebuild_reconciliation(tmp_path):
    """Blocker 4 (strengthened): retain one chunk, remove another, update a third.

    Exercises reconciliation between retained / updated / removed records, not
    just 'delete everything'.
    """
    import shutil
    from scripts.aivsb.retrieval.chunk_extractor import extract_from_path
    from scripts.aivsb.retrieval.index_store import (
        sync_chunks, count_chunks, count_embeddings, upsert_embedding,
    )
    from scripts.aivsb.retrieval.embed_worker import SHIPPING_MODEL

    src = Path(SRC)
    tmp_src = tmp_path / "src"
    (tmp_src / "style_guides").mkdir(parents=True)
    shutil.copy(src / "style_guides" / "en.yaml", tmp_src / "style_guides" / "en.yaml")

    v1 = extract_from_path(tmp_src / "style_guides" / "en.yaml", tmp_src)
    assert len(v1) >= 3, "need >=3 chunks to exercise reconciliation"
    sync_chunks(tmp_path, v1)
    # give an embedding to a chunk we will REMOVE, to confirm FK cascade on deletion
    removed_ids = {c.chunk_id for c in v1[2:]}
    victim = v1[2]
    upsert_embedding(tmp_path, victim.chunk_id, SHIPPING_MODEL, None, 384, b"\x00" * 16, victim.content_hash)
    assert count_embeddings(tmp_path) == 1

    # v2: keep v1[0] and v1[1]; drop v1[2:] (remove); v1[0] retained as-is
    kept = v1[:2]
    written, removed = sync_chunks(tmp_path, kept)
    assert removed == len(removed_ids), f"stale not removed: {removed} vs {len(removed_ids)}"
    assert count_chunks(tmp_path) == 2, "only retained chunks should remain"
    # the removed victim's embedding must be cascade-gone
    assert count_embeddings(tmp_path) == 0, "cascade delete of embedding failed"
    # retained chunk still present
    remaining = {r[0] for r in __import__("automation_db", fromlist=["connect"]).connect(tmp_path).execute("SELECT chunk_id FROM retrieval_chunks")}
    assert v1[0].chunk_id in remaining and v1[1].chunk_id in remaining


@requires_source
def test_sync_chunks_atomic_rollback(tmp_path):
    """Blocker 1: sync_chunks must be one transaction; a mid-sync failure rolls back.

    Inject a failure into the stale-delete phase. On rollback:
      - the attempted upserts from that sync must NOT persist,
      - no chunks may be deleted,
      - no embeddings may be cascade-deleted,
      - the exception must propagate.
    """
    import shutil
    from scripts.aivsb.retrieval.chunk_extractor import extract_from_path
    from scripts.aivsb.retrieval.index_store import sync_chunks, count_chunks, count_embeddings
    from scripts.aivsb.retrieval import index_store

    src = Path(SRC)
    tmp_src = tmp_path / "src"
    (tmp_src / "style_guides").mkdir(parents=True)
    shutil.copy(src / "style_guides" / "en.yaml", tmp_src / "style_guides" / "en.yaml")
    v1 = extract_from_path(tmp_src / "style_guides" / "en.yaml", tmp_src)
    sync_chunks(tmp_path, v1)
    before = count_chunks(tmp_path)
    assert before == len(v1)

    # Capture pre-state directly from the DB.
    conn = index_store._connect(tmp_path)
    try:
        before_chunk_ids = {r[0] for r in conn.execute(
            "SELECT chunk_id FROM retrieval_chunks ORDER BY chunk_id")}
        before_embedding_count = count_embeddings(tmp_path)
    finally:
        conn.close()

    # Wrap the connection's execute so a stale-delete raises after the upsert
    # phase but before commit. (sqlite3.Connection.execute is read-only, so we
    # wrap via the _Conn adapter returned by index_store._connect.)
    real_connect = index_store._connect
    injected = {"count": 0}

    def patched_connect(root):
        c = real_connect(root)
        real_execute = c.execute

        def failing_execute(sql, params=()):
            normalized = sql.strip().upper()
            if normalized.startswith("DELETE FROM RETRIEVAL_CHUNKS WHERE CHUNK_ID"):
                injected["count"] += 1
                raise sqlite3.OperationalError("injected delete failure")
            return real_execute(sql, params)

        c.execute = failing_execute
        return c

    index_store._connect = patched_connect
    try:
        with pytest.raises(sqlite3.OperationalError, match="injected delete failure"):
            # kept has fewer chunks -> triggers a stale DELETE which fails -> rollback
            sync_chunks(tmp_path, v1[:1])
    finally:
        index_store._connect = real_connect

    # The injection must have actually fired (otherwise the test is vacuous).
    assert injected["count"] == 1, "injected failure did not trigger the stale-delete path"

    # After rollback, the index must be unchanged.
    after_conn = index_store._connect(tmp_path)
    try:
        after_chunk_ids = {r[0] for r in after_conn.execute(
            "SELECT chunk_id FROM retrieval_chunks ORDER BY chunk_id")}
    finally:
        after_conn.close()
    assert after_chunk_ids == before_chunk_ids, "rollback failed: chunks were mutated"
    assert count_chunks(tmp_path) == before, "rollback failed: chunk count changed"
    assert count_embeddings(tmp_path) == before_embedding_count, \
        "rollback failed: embeddings were cascade-deleted"