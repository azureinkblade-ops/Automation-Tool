"""Slice 1 provenance follow-up -- run-level retrieval index metadata.

Answers: which AIVSB source state, extractor implementation, and embedding
configuration produced the current derived retrieval index?

This module is read/write for index provenance only. Retrieval consumers must
NOT write provenance (see AIVSB-RETRIEVAL-PROVENANCE handoff). It does not change
retrieval ranking, prompt composition, feature flags, or Slice 2 consumer behavior.

Lifecycle is two-phase (audit-friendly): a STARTED record is committed before the
index mutation, so a failed run remains evidenced even if the mutation rolls back.

Schema decision: SCHEMA_VERSION advanced 6 -> 7 for retrieval_index_runs /
retrieval_index_run_chunks because these are durable governance/audit metadata,
not a rebuildable derived cache. See handoff.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import automation_db as adb

from .chunk_extractor import KnowledgeChunk

EXTRACTOR_VERSION = "slice1-extractor-v1"

# Subprocess git invocations are isolated here so tests can mock this function.
def _git(*args: str, cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=10
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None


@dataclass(frozen=True)
class IndexRunProvenance:
    run_id: str
    canonical_repo_root: str
    source_git_commit: str | None
    source_git_dirty: bool
    extractor_version: str
    embedding_model: str | None
    embedding_revision: str | None
    manifest_hash: str


def collect_git_state(source_root: Path) -> tuple[str | None, bool]:
    """Return (commit_sha_or_None, dirty).

    Git clean        -> (sha, False)
    Git modified     -> (sha, True)
    Not a git repo   -> (None, False)  # manifest hash is the source-state identity
    No fabricated commit is ever recorded.
    """
    sha = _git("rev-parse", "HEAD", cwd=source_root)
    if sha is None:
        return None, False
    dirty = _git("status", "--porcelain", cwd=source_root) not in ("", None)
    return sha, bool(dirty)


def _content_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build_index_manifest(
    source_root: Path,
    chunks: Sequence[KnowledgeChunk],
    *,
    extractor_version: str,
    embedding_model: str | None,
    embedding_revision: str | None,
) -> str:
    """Deterministic SHA-256 over the indexed source state.

    Includes (sorted, stable): normalized relative path, file content sha,
    extractor version, embedding model/revision. Excludes timestamps, absolute
    paths, row order, and machine-specific temp paths. Same source + config ->
    same hash.
    """
    # Map each chunk to its source file; dedupe by relative path.
    rel_paths = sorted({c.source_file for c in chunks})
    lines: list[str] = []
    for rel in rel_paths:
        abs_path = source_root / rel
        if abs_path.exists():
            lines.append(f"{rel}:{_content_hash(abs_path)}")
        else:
            # Allow a chunk whose source file is absent (defensive); still stable.
            lines.append(f"{rel}:MISSING")
    lines.append(f"extractor_version:{extractor_version}")
    lines.append(f"embedding_model:{embedding_model}")
    lines.append(f"embedding_revision:{embedding_revision}")
    canonical = "\n".join(lines)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def begin_index_run(root: Path, provenance: IndexRunProvenance) -> str:
    """Insert a STARTED run record (committed immediately). Returns run_id."""
    conn = adb.connect(root)
    try:
        conn.execute(
            """
            INSERT INTO retrieval_index_runs
                (run_id, canonical_repo_root, source_git_commit, source_git_dirty,
                 extractor_version, embedding_model, embedding_revision,
                 manifest_hash, chunk_count, embedding_count, started_at, status)
            VALUES (:run_id, :root, :commit, :dirty, :extractor, :model,
                    :revision, :manifest, 0, 0, :started, 'STARTED')
            """,
            {
                "run_id": provenance.run_id,
                "root": provenance.canonical_repo_root,
                "commit": provenance.source_git_commit,
                "dirty": 1 if provenance.source_git_dirty else 0,
                "extractor": provenance.extractor_version,
                "model": provenance.embedding_model,
                "revision": provenance.embedding_revision,
                "manifest": provenance.manifest_hash,
                "started": _now(),
            },
        )
        conn.commit()
    finally:
        conn.close()
    return provenance.run_id


def _insert_membership(root: Path, run_id: str, chunks: Sequence[KnowledgeChunk]) -> None:
    conn = adb.connect(root)
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO retrieval_index_run_chunks
                (run_id, chunk_id, content_hash)
            VALUES (?, ?, ?)
            """,
            [(run_id, c.chunk_id, c.content_hash) for c in chunks],
        )
        conn.commit()
    finally:
        conn.close()


def complete_index_run(
    root: Path,
    run_id: str,
    *,
    chunk_ids: Sequence[str],
    chunk_count: int,
    embedding_count: int,
) -> None:
    """Mark a run COMPLETED and record final counts + membership snapshot."""
    conn = adb.connect(root)
    try:
        conn.execute(
            """
            UPDATE retrieval_index_runs
            SET status='COMPLETED', completed_at=:done,
                chunk_count=:cc, embedding_count=:ec
            WHERE run_id=:rid
            """,
            {"done": _now(), "cc": chunk_count, "ec": embedding_count, "rid": run_id},
        )
        conn.commit()
    finally:
        conn.close()
    # Membership snapshot is recorded from the live chunks at completion time.
    _insert_membership(root, run_id, _chunks_by_ids(root, chunk_ids))


def fail_index_run(root: Path, run_id: str, error: Exception) -> None:
    """Mark a run FAILED and record the error summary. Never marks COMPLETED."""
    conn = adb.connect(root)
    try:
        conn.execute(
            """
            UPDATE retrieval_index_runs
            SET status='FAILED', completed_at=:done,
                error_message=:err
            WHERE run_id=:rid
            """,
            {"done": _now(), "err": f"{type(error).__name__}: {error}", "rid": run_id},
        )
        conn.commit()
    finally:
        conn.close()


def _chunks_by_ids(root: Path, chunk_ids: Sequence[str]) -> list[KnowledgeChunk]:
    if not chunk_ids:
        return []
    conn = adb.connect(root)
    try:
        rows = conn.execute(
            "SELECT chunk_id, novel_id, domain, character_id, platform, asset_type, "
            "status, version, content_hash, summary, body, tags, source_file, "
            "chunk_path, updated_at FROM retrieval_chunks "
            "WHERE chunk_id IN ({})".format(",".join("?" * len(chunk_ids))),
            list(chunk_ids),
        ).fetchall()
    finally:
        conn.close()
    return [KnowledgeChunk(
        chunk_id=r["chunk_id"], novel_id=r["novel_id"], domain=r["domain"],
        character_id=r["character_id"], platform=r["platform"], asset_type=r["asset_type"],
        status=r["status"], version=r["version"], content_hash=r["content_hash"],
        summary=r["summary"], body=r["body"], tags=r["tags"],
        source_file=r["source_file"], chunk_path=r["chunk_path"], updated_at=r["updated_at"],
    ) for r in rows]


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def run_index(
    root: Path,
    source_root: Path,
    chunks: Sequence[KnowledgeChunk],
    *,
    embedding_model: str | None,
    embedding_revision: str | None,
    run_id: str | None = None,
) -> str:
    """Two-phase index run with provenance.

    Phase 1: collect git state + build manifest, insert STARTED record (committed).
    Phase 2: atomically sync_chunks (Slice 1) + insert membership snapshot, then
    mark COMPLETED. On any failure in phase 2, mark FAILED and propagate.

    Does NOT change retrieval ranking/flags/Slice 2. Returns run_id.
    """
    from .index_store import sync_chunks, count_embeddings

    canonical_root = str(source_root.resolve())
    commit, dirty = collect_git_state(source_root)
    manifest = build_index_manifest(
        source_root, chunks,
        extractor_version=EXTRACTOR_VERSION,
        embedding_model=embedding_model,
        embedding_revision=embedding_revision,
    )
    rid = run_id or (_now() + "-" + manifest[:12])
    prov = IndexRunProvenance(
        run_id=rid, canonical_repo_root=canonical_root,
        source_git_commit=commit, source_git_dirty=dirty,
        extractor_version=EXTRACTOR_VERSION,
        embedding_model=embedding_model, embedding_revision=embedding_revision,
        manifest_hash=manifest,
    )
    begin_index_run(root, prov)  # committed STARTED record
    try:
        written, removed = sync_chunks(root, chunks)
        emb_count = count_embeddings(root)
        complete_index_run(
            root, rid,
            chunk_ids=[c.chunk_id for c in chunks],
            chunk_count=len(chunks), embedding_count=emb_count,
        )
    except Exception as exc:
        fail_index_run(root, rid, exc)
        raise
    return rid
