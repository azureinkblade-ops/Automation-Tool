"""Slice 1 — CLI for the Knowledge Retrieval Engine.

Subcommands:
  index   - extract chunks from AIVSB_SOURCE_PATH, embed (if available), store
  query   - run retrieve() against a query
  stats   - show chunk / embedding counts

AIVSB_SOURCE_PATH is a REQUIRED deployment input (env or local config). It is
validated at startup; if absent or invalid, the CLI fails clearly and does NOT
fall back to the vault, an empty corpus, or a repo-local copy.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Root of the Automation Tool repo (where automation_db lives).
REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_source_path() -> Path:
    raw = os.environ.get("AIVSB_SOURCE_PATH", "")
    if not raw:
        sys.exit(
            "ERROR: AIVSB_SOURCE_PATH is not set. It is a required deployment input.\n"
            "Set it to the external AIVSB canonical repository path (e.g. export "
            "AIVSB_SOURCE_PATH='C:/path/to/Inkblade Author Studio/scripts/aivsb').\n"
            "The corpus is NOT copied, vendored, or substituted."
        )
    p = Path(raw)
    if not p.exists() or not p.is_dir():
        sys.exit(f"ERROR: AIVSB_SOURCE_PATH does not exist or is not a directory: {raw}")
    # sanity: require at least one allowlisted KB file present
    from .chunk_extractor import ALLOWED_RELATIVE_PATHS
    if not any((p / rel).exists() for rel in ALLOWED_RELATIVE_PATHS):
        sys.exit(
            f"ERROR: AIVSB_SOURCE_PATH has no allowlisted KB YAML files: {raw}\n"
            "Expected files such as camera_intents.yaml, style_guides/en.yaml, etc."
        )
    return p


def cmd_index(args: argparse.Namespace) -> int:
    from .chunk_extractor import extract
    from .index_store import upsert_chunks, upsert_embedding, count_chunks, count_embeddings
    from .embed_worker import is_available, embed_texts, EmbeddingUnavailable, SHIPPING_MODEL

    src = resolve_source_path()
    chunks = list(extract(src))
    n = upsert_chunks(REPO_ROOT, chunks)
    print(f"Indexed {n} chunks from {src}")

    if is_available():
        try:
            model, rev, dim, packed = embed_texts([c.body for c in chunks])
            for c, vec in zip(chunks, packed):
                upsert_embedding(REPO_ROOT, c.chunk_id, model, rev, dim, vec, c.content_hash)
            print(f"Embedded {len(packed)} chunks with {model} (dim={dim})")
        except EmbeddingUnavailable as e:
            print(f"WARN: embedding unavailable ({e}); stored chunks without vectors. "
                  "retrieve() will use metadata+keyword fallback.")
    else:
        print("WARN: embedding model unavailable; stored chunks without vectors. "
              "retrieve() will use metadata+keyword fallback.")

    print(f"Total chunks: {count_chunks(REPO_ROOT)}, embeddings: {count_embeddings(REPO_ROOT)}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    from .retriever import retrieve
    hits = retrieve(REPO_ROOT, args.query, novel_id=args.novel, domain=args.domain,
                    character_id=args.character, rerank=args.rerank, top_n=args.top_n)
    for i, h in enumerate(hits, 1):
        print(f"{i}. [{h.score:.3f}] {h.domain}/{h.novel_id} {h.chunk_id}")
        print(f"   {h.summary}")
        print(f"   prov: {h.provenance}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from .index_store import count_chunks, count_embeddings
    print(f"chunks: {count_chunks(REPO_ROOT)}")
    print(f"embeddings: {count_embeddings(REPO_ROOT)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aivsb-retrieval", description="Slice 1 retrieval CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("index", help="extract + embed + store from AIVSB_SOURCE_PATH")
    pi.set_defaults(func=cmd_index)

    pq = sub.add_parser("query", help="run retrieve()")
    pq.add_argument("query")
    pq.add_argument("--novel")
    pq.add_argument("--domain")
    pq.add_argument("--character")
    pq.add_argument("--top-n", type=int, default=10)
    pq.add_argument("--rerank", action="store_true")
    pq.set_defaults(func=cmd_query)

    ps = sub.add_parser("stats", help="show counts")
    ps.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
