"""Slice 1 — KnowledgeChunk extractor.

Reads the AIVSB YAML corpus from an EXTERNAL canonical source (resolved via
AIVSB_SOURCE_PATH) and emits KnowledgeChunk records. This module is read-only
against the source; it never writes Bible content.

Contract (from SLICE1-OWNERSHIP-PROPOSAL + SLICE1-AUTOMATION-DB-HANDOFF):
- Ingestion is restricted to an allowlist of KB YAML files / explicit KB locations.
- Recursive scanning of the whole external repo is prohibited.
- .model-acquisition/, venvs, experiment outputs, .git/, and unrelated files excluded.
- Supports BOTH mapping-rooted docs (chunk per top-level key) and list-rooted docs
  (chunk per list element).
- Chunk IDs are stable: <relative-path>::<json-path>, deterministic across runs.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

import yaml

# ---- Allowlist: relative paths (posix) under AIVSB_SOURCE_PATH, repo-root-anchored ----
# These are the 17 verified KB YAML files (excludes venvs / experiment / .git).
ALLOWED_RELATIVE_PATHS = frozenset({
    "camera_intents.yaml",
    "lighting_intents.yaml",
    "cinematic_language.yaml",
    "scene_grammar.yaml",
    "scene_taxonomy.yaml",
    "render_rules.yaml",
    "studio_memory.yaml",
    "production_analytics.yaml",
    "characters/kael.yaml",
    "characters/kai.yaml",
    "characters/liang.yaml",
    "characters/sf_protagonists.yaml",
    "locations/locations.yaml",
    "style_guides/en.yaml",
    "style_guides/ha.yaml",
    "style_guides/sf.yaml",
    "style_guides/hp.yaml",
})

# Directories that must never be scanned.
EXCLUDED_DIR_FRAGMENTS = (".model-acquisition", ".venv", "venv", "__pycache__",
                          ".git", "evals", "retrieval/stage_c", "retrieval/stage_c_out",
                          "bench_results", "artifacts", "reasoning")


@dataclass
class KnowledgeChunk:
    chunk_id: str
    novel_id: str
    domain: str
    character_id: str | None
    platform: str | None
    asset_type: str | None
    status: str
    version: str
    content_hash: str
    summary: str
    body: str
    tags: list[str]
    source_file: str
    chunk_path: str
    updated_at: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        d["tags"] = json.dumps(self.tags, ensure_ascii=False)
        return d


def _domain_for(rel_path: str) -> str:
    """Map a relative source path to a retrieval domain (seed mapping from plan)."""
    p = rel_path.lower()
    if p.startswith("characters/"):
        return "character"
    if p.startswith("style_guides/"):
        return "visual_identity"
    if p in ("camera_intents.yaml", "lighting_intents.yaml"):
        return "visual_identity"
    if p in ("cinematic_language.yaml", "scene_grammar.yaml", "scene_taxonomy.yaml"):
        return "video"
    if p in ("studio_memory.yaml", "production_analytics.yaml"):
        return "lesson"
    if p == "render_rules.yaml":
        return "video"
    if p.startswith("locations/"):
        return "location"
    return "worldbuilding"


def _novel_id_for(rel_path: str, node: Any) -> str:
    """Best-effort novel_id: from style_guides filename, else 'studio' (shared)."""
    p = rel_path.lower()
    if p.startswith("style_guides/"):
        stem = Path(p).stem  # en/ha/sf/hp
        return {"en": "en", "ha": "ha", "sf": "sf", "hp": "hp"}.get(stem, "studio")
    return "studio"


def _stable_id(rel_path: str, json_path: str) -> str:
    return f"{rel_path}::{json_path}"


def _summarize(body_text: str, max_chars: int = 200) -> str:
    first_line = body_text.strip().splitlines()[0] if body_text.strip() else ""
    s = first_line.strip()
    return s[:max_chars]


def _iter_nodes(node: Any, prefix: str):
    """Yield (json_path, value) for chunkable units."""
    if isinstance(node, dict):
        for k, v in node.items():
            child = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                yield from _iter_nodes(v, child)
            else:
                yield child, v
    elif isinstance(node, list):
        for i, v in enumerate(node):
            child = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                yield from _iter_nodes(v, child)
            else:
                yield child, v


def _extract_from_doc(rel_path: str, data: Any, file_text: str, version: str):
    """Yield KnowledgeChunk objects from one parsed YAML document."""
    chunks: list[KnowledgeChunk] = []
    novel_id = _novel_id_for(rel_path, data)
    domain = _domain_for(rel_path)
    content_hash = hashlib.sha256(file_text.encode("utf-8")).hexdigest()

    def make_chunk(json_path: str, body_node: Any) -> KnowledgeChunk:
        body_text = yaml.safe_dump(body_node, allow_unicode=True, sort_keys=False)
        return KnowledgeChunk(
            chunk_id=_stable_id(rel_path, json_path),
            novel_id=novel_id,
            domain=domain,
            character_id=(Path(rel_path).stem if rel_path.startswith("characters/") else None),
            platform=None,
            asset_type=None,
            status="approved",
            version=version,
            content_hash=content_hash,
            summary=_summarize(body_text),
            body=body_text,
            tags=[rel_path.split("/")[0], domain],
            source_file=rel_path,
            chunk_path=json_path,
        )

    if isinstance(data, dict):
        # mapping-rooted: chunk per top-level key (and recurse into nested dict/list).
        for k, v in data.items():
            json_path = str(k)
            if isinstance(v, (dict, list)):
                # recurse to produce finer-grained chunks; keep the top-level too.
                for sub_path, _ in _iter_nodes(v, json_path):
                    pass  # sub-paths handled below
                # top-level block as one chunk
                chunks.append(make_chunk(json_path, v))
                # finer chunks per leaf-group
                for sub_path, sub_val in _iter_nodes(v, json_path):
                    if isinstance(sub_val, (dict, list)):
                        chunks.append(make_chunk(sub_path, sub_val))
            else:
                chunks.append(make_chunk(json_path, v))
    elif isinstance(data, list):
        # list-rooted: chunk per list element (e.g. sf_protagonists, locations).
        for i, item in enumerate(data):
            chunks.append(make_chunk(f"[{i}]", item))
    else:
        # scalar doc: single chunk.
        chunks.append(make_chunk("", data))

    # de-duplicate by chunk_id (keep first), preserving order
    seen = set()
    for c in chunks:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        yield c


def _version_of(path: Path) -> str:
    try:
        import os
        st = os.stat(path)
        return hashlib.sha256(f"{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


def iter_allowed_files(source_root: Path) -> Iterable[Path]:
    """Yield only allowlisted KB YAML files under source_root (no recursive repo scan)."""
    for rel in ALLOWED_RELATIVE_PATHS:
        p = source_root / rel
        if p.exists() and p.is_file():
            yield p


def extract(source_root: Path) -> Iterable[KnowledgeChunk]:
    """Extract KnowledgeChunks from the allowlisted AIVSB KB YAML files.

    `source_root` is the resolved AIVSB_SOURCE_PATH. Only allowlisted files are read.
    """
    for path in iter_allowed_files(source_root):
        rel = str(path.relative_to(source_root)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        version = _version_of(path)
        yield from _extract_from_doc(rel, data, text, version)


def extract_from_path(path: Path, source_root: Path) -> list[KnowledgeChunk]:
    """Extract chunks from a single allowlisted file (used by tests / CLI)."""
    rel = str(path.relative_to(source_root)).replace("\\", "/")
    if rel not in ALLOWED_RELATIVE_PATHS:
        raise ValueError(f"Path not in ingestion allowlist: {rel}")
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    version = _version_of(path)
    return list(_extract_from_doc(rel, data, text, version))
