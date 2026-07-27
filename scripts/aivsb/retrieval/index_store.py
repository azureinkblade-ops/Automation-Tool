"""Slice 1 — SQLite index store for KnowledgeChunks + embeddings.

Writes into the retrieval_chunks / chunk_embeddings tables created by the
SLICE1-AUTOMATION-DB-HANDOFF migration in automation_db.py. This module only
reads/writes those two tables; it never touches other automation_db features.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import sqlite3

import automation_db as adb

from .chunk_extractor import KnowledgeChunk


def _connect(root: Path) -> "_Conn":
    # Ensure the schema (incl. retrieval_chunks / chunk_embeddings from the
    # SLICE1 handoff migration) exists, then return an open connection wrapper.
    adb.init_db(root)
    return _Conn(adb.connect(root))


class _Conn:
    """Thin adapter over a real sqlite3.Connection.

    Exists so tests can inject failure behavior: sqlite3.Connection.execute is a
    read-only attribute and cannot be monkeypatched, but _Conn.execute is a normal
    method. All other behavior delegates to the wrapped connection.
    """

    def __init__(self, raw: sqlite3.Connection):
        self._raw = raw

    def execute(self, sql, *args, **kwargs):
        return self._raw.execute(sql, *args, **kwargs)

    def executemany(self, sql, *args, **kwargs):
        return self._raw.executemany(sql, *args, **kwargs)

    def executescript(self, sql, *args, **kwargs):
        return self._raw.executescript(sql, *args, **kwargs)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()

    def __getattr__(self, name):
        return getattr(self._raw, name)



def delete_chunk(root: Path, chunk_id: str) -> None:
    conn = _connect(root)
    try:
        conn.execute("DELETE FROM retrieval_chunks WHERE chunk_id=?", (chunk_id,))
        conn.commit()
    finally:
        conn.close()


def sync_chunks(root: Path, chunks: Iterable[KnowledgeChunk]) -> tuple[int, int]:
    """Atomically insert/update chunks AND remove stale records absent from `chunks`.

    Returns (written, removed). Both operations run in a SINGLE connection and a
    SINGLE transaction; any exception rolls back the whole operation, so there is
    no intermediate state where new chunks are committed but stale chunks remain.

    This makes the index rebuildable: re-running extraction + sync_chunks drops
    chunks/embeddings whose source entry was removed, so removed YAML content
    cannot remain retrievable indefinitely. Embeddings are cascade-deleted via the
    FK (PRAGMA foreign_keys=ON in automation_db.connect).
    """
    chunk_list = list(chunks)
    wanted_ids = {c.chunk_id for c in chunk_list}
    conn = _connect(root)
    written = 0
    removed = 0
    try:
        # 1) upsert phase (single connection, not the separate-commit upsert_chunks)
        for c in chunk_list:
            row = c.to_row()
            conn.execute(
                """
                INSERT INTO retrieval_chunks
                    (chunk_id, novel_id, domain, character_id, platform, asset_type,
                     status, version, content_hash, summary, body, tags,
                     source_file, chunk_path, updated_at)
                VALUES (:chunk_id, :novel_id, :domain, :character_id, :platform, :asset_type,
                        :status, :version, :content_hash, :summary, :body, :tags,
                        :source_file, :chunk_path, :updated_at)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    novel_id=excluded.novel_id, domain=excluded.domain,
                    character_id=excluded.character_id, platform=excluded.platform,
                    asset_type=excluded.asset_type, status=excluded.status,
                    version=excluded.version, content_hash=excluded.content_hash,
                    summary=excluded.summary, body=excluded.body, tags=excluded.tags,
                    source_file=excluded.source_file, chunk_path=excluded.chunk_path,
                    updated_at=excluded.updated_at
                """,
                row,
            )
            written += 1
        # 2) stale-delete phase (same connection, same transaction)
        existing = [r[0] for r in conn.execute("SELECT chunk_id FROM retrieval_chunks").fetchall()]
        stale = [cid for cid in existing if cid not in wanted_ids]
        for cid in stale:
            conn.execute("DELETE FROM retrieval_chunks WHERE chunk_id=?", (cid,))
            removed += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return written, removed


def upsert_chunks(root: Path, chunks: Iterable[KnowledgeChunk]) -> int:
    """Insert/replace chunk rows. Returns count written."""
    conn = _connect(root)
    n = 0
    try:
        for c in chunks:
            row = c.to_row()
            conn.execute(
                """
                INSERT INTO retrieval_chunks
                    (chunk_id, novel_id, domain, character_id, platform, asset_type,
                     status, version, content_hash, summary, body, tags,
                     source_file, chunk_path, updated_at)
                VALUES (:chunk_id, :novel_id, :domain, :character_id, :platform, :asset_type,
                        :status, :version, :content_hash, :summary, :body, :tags,
                        :source_file, :chunk_path, :updated_at)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    novel_id=excluded.novel_id, domain=excluded.domain,
                    character_id=excluded.character_id, platform=excluded.platform,
                    asset_type=excluded.asset_type, status=excluded.status,
                    version=excluded.version, content_hash=excluded.content_hash,
                    summary=excluded.summary, body=excluded.body, tags=excluded.tags,
                    source_file=excluded.source_file, chunk_path=excluded.chunk_path,
                    updated_at=excluded.updated_at
                """,
                row,
            )
            n += 1
        conn.commit()
    finally:
        conn.close()
    return n


def delete_embedding_for(root: Path, chunk_id: str) -> None:
    conn = _connect(root)
    try:
        conn.execute("DELETE FROM chunk_embeddings WHERE chunk_id=?", (chunk_id,))
        conn.commit()
    finally:
        conn.close()


def upsert_embedding(root: Path, chunk_id: str, model: str, revision: str | None,
                     dim: int, vector_bytes: bytes, content_hash: str) -> None:
    from .embed_worker import utc_now_text
    conn = _connect(root)
    try:
        conn.execute(
            """
            INSERT INTO chunk_embeddings
                (chunk_id, embedding_model, embedding_revision, embedding_dim,
                 embedded_at, content_hash, vector)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                embedding_model=excluded.embedding_model,
                embedding_revision=excluded.embedding_revision,
                embedding_dim=excluded.embedding_dim,
                embedded_at=excluded.embedded_at,
                content_hash=excluded.content_hash,
                vector=excluded.vector
            """,
            (chunk_id, model, revision, dim, utc_now_text(), content_hash, vector_bytes),
        )
        conn.commit()
    finally:
        conn.close()


def count_chunks(root: Path) -> int:
    conn = _connect(root)
    try:
        return conn.execute("SELECT COUNT(*) FROM retrieval_chunks").fetchone()[0]
    finally:
        conn.close()


def count_embeddings(root: Path) -> int:
    conn = _connect(root)
    try:
        return conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
    finally:
        conn.close()
