"""Slice 1 retrieval package."""
from .chunk_extractor import KnowledgeChunk, extract, extract_from_path, ALLOWED_RELATIVE_PATHS
from .retriever import retrieve, RetrievalHit
from .index_store import upsert_chunks, sync_chunks, delete_chunk, count_chunks, count_embeddings
from .embed_worker import SHIPPING_MODEL, MODEL_REVISION, is_available
from .provenance import (
    EXTRACTOR_VERSION, IndexRunProvenance, build_index_manifest,
    collect_git_state, begin_index_run, complete_index_run, fail_index_run, run_index,
)

__all__ = [
    "KnowledgeChunk", "extract", "extract_from_path", "ALLOWED_RELATIVE_PATHS",
    "retrieve", "RetrievalHit", "upsert_chunks", "sync_chunks", "delete_chunk",
    "count_chunks", "count_embeddings",
    "SHIPPING_MODEL", "MODEL_REVISION", "is_available",
    "EXTRACTOR_VERSION", "IndexRunProvenance", "build_index_manifest",
    "collect_git_state", "begin_index_run", "complete_index_run", "fail_index_run",
    "run_index",
]
