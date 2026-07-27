"""Slice 1 — hybrid retrieve() API (metadata-first, then semantic within scope).

Execution order (Q2, from SLICE1 plan):
1. Hard metadata filters (novel_id/domain/character/platform/status) -> SQL WHERE.
2. Structured-reference resolution (explicit refs merged) - reserved, currently no-op.
3. Semantic (MiniLM cosine) WITHIN the filtered candidates.
4. Optional rerank (cross-encoder) - lazy import, degrades to cosine if absent.
5. Canon-boundary validation: if novel_id given, DROP any hit whose novel_id != requested.
6. Return RetrievalHit list with provenance.

If the embedding model is unavailable, semantic step degrades to metadata+keyword
(BM25-lite) scoring over body/summary/tags and logs a warning. No exception.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import automation_db as adb

from .embed_worker import is_available, embed_texts, EmbeddingUnavailable, SHIPPING_MODEL


@dataclass
class RetrievalHit:
    chunk_id: str
    novel_id: str
    domain: str
    score: float
    summary: str
    provenance: dict


def _keyword_score(query: str, body: str, summary: str, tags: str) -> float:
    q = query.lower()
    hay = f"{summary} {body} {tags}".lower()
    if not q or not hay:
        return 0.0
    # crude BM25-lite: term overlap with length normalization
    terms = q.split()
    hits = sum(1 for t in terms if t in hay)
    return hits / math.sqrt(len(hay) + 1)


def retrieve(root: Path, query: str, novel_id: Optional[str] = None,
             domain: Optional[str] = None, character_id: Optional[str] = None,
             platform: Optional[str] = None, asset_type: Optional[str] = None,
             status: str = "approved", top_n: int = 10, rerank: bool = False
             ) -> list[RetrievalHit]:
    conn = adb.connect(root)
    try:
        where = ["status=?"]
        params = [status]
        if novel_id is not None:
            where.append("novel_id=?")
            params.append(novel_id)
        if domain is not None:
            where.append("domain=?")
            params.append(domain)
        if character_id is not None:
            where.append("character_id=?")
            params.append(character_id)
        if platform is not None:
            where.append("platform=?")
            params.append(platform)
        if asset_type is not None:
            where.append("asset_type=?")
            params.append(asset_type)
        sql = (
            "SELECT chunk_id, novel_id, domain, summary, body, tags, source_file, "
            "chunk_path, version, content_hash FROM retrieval_chunks WHERE "
            + " AND ".join(where)
        )
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    # Step 5 guard: if novel_id requested, enforce canon boundary (defense in depth).
    if novel_id is not None:
        rows = [r for r in rows if r[1] == novel_id]

    candidates = []
    semantic_ok = False
    try:
        if is_available():
            model, rev, dim, packed = embed_texts([query])
            import numpy as np
            qvec = np.frombuffer(packed[0], dtype="float32")
            # fetch embeddings for candidates
            econn = adb.connect(root)
            try:
                emb = {
                    r[0]: np.frombuffer(r[1], dtype="float32")
                    for r in econn.execute(
                        "SELECT chunk_id, vector FROM chunk_embeddings WHERE chunk_id IN (%s)"
                        % ",".join("?" * len(rows)),
                        [r[0] for r in rows],
                    ).fetchall()
                }
            finally:
                econn.close()
            for r in rows:
                cid = r[0]
                if cid in emb:
                    denom = (np.linalg.norm(qvec) * np.linalg.norm(emb[cid])) or 1.0
                    score = float(np.dot(qvec, emb[cid]) / denom)
                    candidates.append((score, r))
            semantic_ok = True
    except EmbeddingUnavailable:
        semantic_ok = False

    if not semantic_ok:
        # CPU/keyword fallback (no exception)
        for r in rows:
            score = _keyword_score(query, r[4], r[3], r[5])
            candidates.append((score, r))

    if rerank and semantic_ok:
        try:
            from sentence_transformers import CrossEncoder
            ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2", device="cpu")
            pairs = [(query, r[4]) for _, r in candidates]
            scores = ce.predict(pairs)
            candidates = sorted(
                zip(scores.tolist(), [r for _, r in candidates]),
                key=lambda x: x[0], reverse=True,
            )
        except Exception:
            candidates.sort(key=lambda x: x[0], reverse=True)
    else:
        candidates.sort(key=lambda x: x[0], reverse=True)

    out = []
    for score, r in candidates[:top_n]:
        out.append(RetrievalHit(
            chunk_id=r[0], novel_id=r[1], domain=r[2], score=float(score),
            summary=r[3],
            provenance={"source_file": r[6], "chunk_path": r[7],
                        "version": r[8], "content_hash": r[9]},
        ))
    return out
