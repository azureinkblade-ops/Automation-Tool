"""Slice 1 retrieval package."""
from .chunk_extractor import KnowledgeChunk, extract, extract_from_path, ALLOWED_RELATIVE_PATHS
from .retriever import retrieve, RetrievalHit
from .index_store import upsert_chunks, sync_chunks, count_chunks, count_embeddings, delete_chunk
from .embed_worker import SHIPPING_MODEL, is_available

__all__ = [
    "KnowledgeChunk", "extract", "extract_from_path", "ALLOWED_RELATIVE_PATHS",
    "retrieve", "RetrievalHit", "upsert_chunks", "sync_chunks", "delete_chunk",
    "count_chunks", "count_embeddings",
    "SHIPPING_MODEL", "is_available",
]
