"""Slice 1 provenance follow-up — tests for run-level retrieval index metadata.

Self-contained: uses a temp fixture corpus (copied allowlisted YAML) and mocks
git subprocess calls. No dependency on the real AIVSB_SOURCE_PATH or embedding model.

Run:
  PYTHONPATH=. python -m pytest tests/aivsb/test_retrieval_provenance.py -q
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import tempfile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

import scripts.aivsb.retrieval.provenance as prov
from scripts.aivsb.retrieval.chunk_extractor import extract_from_path, KnowledgeChunk


def _make_fixture(tmp_path: Path) -> Path:
    """Copy a couple of allowlisted YAML files into a temp source tree."""
    src = Path("C:/Users/David/Documents/Inkblade Author Studio/scripts/aivsb")
    tree = tmp_path / "src"
    (tree / "style_guides").mkdir(parents=True)
    (tree / "characters").mkdir(parents=True)
    import shutil
    shutil.copy(src / "style_guides" / "en.yaml", tree / "style_guides" / "en.yaml")
    shutil.copy(src / "characters" / "kael.yaml", tree / "characters" / "kael.yaml")
    return tree


def _chunks(tree: Path):
    cs = list(extract_from_path(tree / "style_guides" / "en.yaml", tree))
    cs += list(extract_from_path(tree / "characters" / "kael.yaml", tree))
    return cs


def _run_row(root: Path, run_id: str):
    conn = __import__("automation_db", fromlist=["connect"]).connect(root)
    try:
        return conn.execute(
            "SELECT run_id, canonical_repo_root, source_git_commit, source_git_dirty, "
            "extractor_version, embedding_model, embedding_revision, manifest_hash, "
            "chunk_count, embedding_count, status, completed_at, error_message "
            "FROM retrieval_index_runs WHERE run_id=?", (run_id,)
        ).fetchone()
    finally:
        conn.close()


def _membership(root: Path, run_id: str):
    conn = __import__("automation_db", fromlist=["connect"]).connect(root)
    try:
        return {(r[0], r[1], r[2]) for r in conn.execute(
            "SELECT run_id, chunk_id, content_hash FROM retrieval_index_run_chunks "
            "WHERE run_id=?", (run_id,))}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Deterministic manifest
# ---------------------------------------------------------------------------
def test_manifest_deterministic(tmp_path):
    tree = _make_fixture(tmp_path)
    cs = _chunks(tree)
    h1 = prov.build_index_manifest(tree, cs, extractor_version=prov.EXTRACTOR_VERSION,
                                   embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    h2 = prov.build_index_manifest(tree, cs, extractor_version=prov.EXTRACTOR_VERSION,
                                   embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


# ---------------------------------------------------------------------------
# 2. Manifest sensitivity
# ---------------------------------------------------------------------------
def test_manifest_sensitivity(tmp_path):
    tree = _make_fixture(tmp_path)
    cs = _chunks(tree)
    base = prov.build_index_manifest(tree, cs, extractor_version=prov.EXTRACTOR_VERSION,
                                     embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    # change embedding model
    changed_model = prov.build_index_manifest(tree, cs, extractor_version=prov.EXTRACTOR_VERSION,
                                              embedding_model="BAAI/bge-m3", embedding_revision=None)
    assert changed_model != base
    # change embedding revision
    changed_rev = prov.build_index_manifest(tree, cs, extractor_version=prov.EXTRACTOR_VERSION,
                                            embedding_model="all-MiniLM-L6-v2", embedding_revision="abc")
    assert changed_rev != base
    # change extractor version
    changed_ext = prov.build_index_manifest(tree, cs, extractor_version="slice1-extractor-v2",
                                            embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    assert changed_ext != base
    # change a YAML file content
    target = tree / "style_guides" / "en.yaml"
    data = target.read_bytes() + b"\n# changed\n"
    target.write_bytes(data)
    changed_file = prov.build_index_manifest(tree, cs, extractor_version=prov.EXTRACTOR_VERSION,
                                             embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    assert changed_file != base


# ---------------------------------------------------------------------------
# 3. Git provenance (mocked subprocess)
# ---------------------------------------------------------------------------
def test_git_provenance_states(tmp_path, monkeypatch):
    tree = _make_fixture(tmp_path)

    # (a) clean git repo
    monkeypatch.setattr(prov, "_git", lambda *a, cwd: "abc123" if a == ("rev-parse", "HEAD") else "")
    commit, dirty = prov.collect_git_state(tree)
    assert commit == "abc123" and dirty is False

    # (b) dirty git repo
    def _git_dirty(*a, cwd):
        if a == ("rev-parse", "HEAD"):
            return "abc123"
        if a == ("status", "--porcelain"):
            return " M style_guides/en.yaml"
        return ""
    monkeypatch.setattr(prov, "_git", _git_dirty)
    commit, dirty = prov.collect_git_state(tree)
    assert commit == "abc123" and dirty is True

    # (c) not a git repo -> commit None, dirty False (no fabricated commit)
    monkeypatch.setattr(prov, "_git", lambda *a, cwd: None)
    commit, dirty = prov.collect_git_state(tree)
    assert commit is None and dirty is False


# ---------------------------------------------------------------------------
# 4. Completed-run persistence
# ---------------------------------------------------------------------------
def test_completed_run_persistence(tmp_path):
    tree = _make_fixture(tmp_path)
    cs = _chunks(tree)
    import automation_db as adb
    root = tmp_path / "db"
    adb.init_db(root)

    # Force a clean-git provenance via mock
    from scripts.aivsb.retrieval import provenance as P
    P._git = lambda *a, cwd: "deadbeef" if a == ("rev-parse", "HEAD") else ""
    rid = P.run_index(root, tree, cs, embedding_model="all-MiniLM-L6-v2", embedding_revision=None)

    row = _run_row(root, rid)
    assert row is not None
    assert row["status"] == "COMPLETED"
    assert row["source_git_commit"] == "deadbeef"
    assert row["source_git_dirty"] == 0
    assert row["extractor_version"] == "slice1-extractor-v1"
    assert row["embedding_model"] == "all-MiniLM-L6-v2"
    assert row["manifest_hash"]
    assert row["chunk_count"] == len(cs)
    assert row["completed_at"] is not None
    assert row["error_message"] is None
    assert Path(row["canonical_repo_root"]) == tree.resolve()


# ---------------------------------------------------------------------------
# 5. Failed-run persistence (injected sync failure)
# ---------------------------------------------------------------------------
def test_failed_run_persistence(tmp_path, monkeypatch):
    tree = _make_fixture(tmp_path)
    cs = _chunks(tree)
    import automation_db as adb
    root = tmp_path / "db"
    adb.init_db(root)

    from scripts.aivsb.retrieval import provenance as P, index_store as istore
    P._git = lambda *a, cwd: "deadbeef" if a == ("rev-parse", "HEAD") else ""

    # Inject a failure into the upsert (INSERT) phase so it fires on a fresh DB.
    real_connect = istore._connect
    def patched(root2):
        c = real_connect(root2)
        real_exec = c.execute
        def fe(sql, params=()):
            norm = sql.strip().upper()
            if norm.startswith("INSERT INTO RETRIEVAL_CHUNKS"):
                raise sqlite3.OperationalError("injected sync failure")
            return real_exec(sql, params)
        c.execute = fe
        return c
    istore._connect = patched
    try:
        with pytest.raises(sqlite3.OperationalError):
            P.run_index(root, tree, cs, embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    finally:
        istore._connect = real_connect

    # The STARTED record must have been committed and then marked FAILED.
    # We cannot know the auto run_id; find the only run row.
    conn = adb.connect(root)
    try:
        rows = conn.execute("SELECT run_id, status, error_message FROM retrieval_index_runs").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert "injected sync failure" in (rows[0]["error_message"] or "")
    assert "COMPLETED" not in {r["status"] for r in rows}


# ---------------------------------------------------------------------------
# 6. Membership accuracy
# ---------------------------------------------------------------------------
def test_membership_accuracy(tmp_path):
    tree = _make_fixture(tmp_path)
    cs = _chunks(tree)
    import automation_db as adb
    root = tmp_path / "db"
    adb.init_db(root)

    from scripts.aivsb.retrieval import provenance as P
    P._git = lambda *a, cwd: "deadbeef" if a == ("rev-parse", "HEAD") else ""
    rid = P.run_index(root, tree, cs, embedding_model="all-MiniLM-L6-v2", embedding_revision=None)

    mem = _membership(root, rid)
    # exactly the chunks present in this run, with their live content_hash
    expected = {(rid, c.chunk_id, c.content_hash) for c in cs}
    assert mem == expected


# ---------------------------------------------------------------------------
# 7. Historical preservation across rebuilds (live row removed, history survives)
# ---------------------------------------------------------------------------
def test_historical_membership_survives_rebuild(tmp_path):
    tree = _make_fixture(tmp_path)
    cs = _chunks(tree)
    import automation_db as adb
    from scripts.aivsb.retrieval import provenance as P, index_store as istore
    root = tmp_path / "db"
    adb.init_db(root)
    P._git = lambda *a, cwd: "deadbeef" if a == ("rev-parse", "HEAD") else ""

    # Run 1: full corpus
    rid1 = P.run_index(root, tree, cs, embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    mem1 = _membership(root, rid1)
    assert len(mem1) == len(cs)

    # Run 2: keep only the first chunk (simulate removal of the rest)
    kept = cs[:1]
    rid2 = P.run_index(root, tree, kept, embedding_model="all-MiniLM-L6-v2", embedding_revision=None)
    mem2 = _membership(root, rid2)
    assert len(mem2) == 1

    # Historical run 1 membership must STILL be queryable, even though most live
    # retrieval_chunks rows were deleted by run 2's sync_chunks.
    mem1_after = _membership(root, rid1)
    assert mem1_after == mem1, "historical run-1 membership was lost on rebuild"

    # The run records are separate provenance entries.
    conn = adb.connect(root)
    try:
        statuses = {r[0]: r[1] for r in conn.execute(
            "SELECT run_id, status FROM retrieval_index_runs")}
    finally:
        conn.close()
    assert statuses[rid1] == "COMPLETED" and statuses[rid2] == "COMPLETED"
    assert len(statuses) == 2
