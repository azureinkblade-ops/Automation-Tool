"""Slice 1 — embedding worker (MiniLM shipping baseline; BGE-M3 parked).

Per SLICE1-OWNERSHIP-PROPOSAL: MiniLM is the shipping baseline. BGE-M3 stays
outside this implementation pending separate evaluation. If sentence_transformers
or the model is unavailable, callers degrade to metadata+keyword scoring (handled
in retriever.py), not a hard failure.

GPU policy: embedding runs on CPU. Never load the embedding model while a render
is active. The corpus is small, so CPU is acceptable.
"""
from __future__ import annotations

import time
from typing import Optional

SHIPPING_MODEL = "all-MiniLM-L6-v2"  # MiniLM-first (deterministic, offline, auditable)
MODEL_REVISION: Optional[str] = None

# These are intentionally NOT used in this slice (parked per plan addendum).
PARKED_MODEL = "BAAI/bge-m3"


def utc_now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class EmbeddingUnavailable(Exception):
    """Raised when the embedding model cannot be loaded (caller degrades)."""


_model = None
_model_loaded = False


def _load() -> None:
    global _model, _model_loaded
    if _model_loaded:
        return
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:  # pragma: no cover - optional dependency
        raise EmbeddingUnavailable(f"sentence_transformers not available: {e}")
    # CPU only; no GPU load (per GPU policy).
    _model = SentenceTransformer(SHIPPING_MODEL, revision=MODEL_REVISION, device="cpu")
    _model_loaded = True


def is_available() -> bool:
    try:
        _load()
        return True
    except EmbeddingUnavailable:
        return False


def embed_texts(texts: list[str]):
    """Return (model_name, revision, dim, list[bytes]) of packed float32 vectors.

    Raises EmbeddingUnavailable if the model cannot load (caller falls back to
    keyword scoring).
    """
    _load()
    import numpy as np
    vecs = _model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    dim = int(vecs.shape[1])
    packed = [np.asarray(v, dtype="float32").tobytes() for v in vecs]
    return SHIPPING_MODEL, MODEL_REVISION, dim, packed


def embed_one(text: str):
    model, rev, dim, packed = embed_texts([text])
    return model, rev, dim, packed[0]
