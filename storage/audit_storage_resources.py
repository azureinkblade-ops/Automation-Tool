"""Read-only repository scanner for storage consolidation.

Strengthens the preliminary 2026-07-22 audit by catching wrapper I/O such as
write_json_atomic(DEEP_TIKTOK_ROTATION_FILE, ...) which a literal-filename scan
misses. It never writes files and never touches the live database.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that must never be scanned for "live" resource access.
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".venv-gpu",
    ".venv-chatterbox",
    ".venv-cpu",
    "node_modules",
    "backup",
    ".hermes/backups",
    "backup",
    ".playwright-profile",
    ".playwright-system-chrome-profile",
    "chrome-helper-profile",
    "output",
    "outputs",
    "image-lab",
    "training-data",
    "loras",
    "experiments",
    "_tmp_tiktok_smoke_assets",
    "_tmp_tiktok_icon",
}

# Roots of generated artifact trees: metadata.json there is a sidecar pattern.
ARTIFACT_ROOT_MARKERS = (
    "content",
    "Promo Images",
    "manual-video-packs",
)

SCAN_EXTENSIONS = (".py", ".js", ".ts", ".bat", ".ps1", ".sh")

# Access patterns to detect. Each tuple: (needle, kind).
# kind in {"read", "write", "read_or_write"}.
ACCESS_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (".read_text(", "read"),
    (".write_text(", "write"),
    (".read_bytes(", "read"),
    (".write_bytes(", "write"),
    ("read_json_safe", "read_or_write"),
    ("write_json_atomic", "write"),
    ("_phase2_load_blob", "read"),
    ("_phase2_save_blob", "write"),
    ("json.load", "read"),
    ("json.dump", "write"),
    ("json.loads", "read"),
    ("json.dumps", "write"),
    ("open(", "read_or_write"),
    ("Path.open", "read_or_write"),
)

# Constant definitions that map a Python name to a legacy JSON filename.
CONST_PATTERN = "= ROOT /"


@dataclass
class AccessSite:
    path: str
    line: int
    snippet: str
    kind: str  # read | write | read_or_write
    symbol: Optional[str] = None  # e.g. SCHEDULE_FILE, DEEP_TIKTOK_ROTATION_FILE


@dataclass
class ScanResult:
    sites: List[AccessSite] = field(default_factory=list)
    constant_map: Dict[str, str] = field(default_factory=dict)
    scanned_files: int = 0

    def by_kind(self, kind: str) -> List[AccessSite]:
        out = []
        for s in self.sites:
            if kind == "write" and s.kind in ("write", "read_or_write"):
                out.append(s)
            elif kind == "read" and s.kind in ("read", "read_or_write"):
                out.append(s)
        return out


def _should_exclude(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)
    if parts & EXCLUDE_DIRS:
        return True
    # Never treat generated artifact directory trees as root-JSON candidates.
    for marker in ARTIFACT_ROOT_MARKERS:
        if marker in parts:
            return True
    return False


def _line_of(txt: str, pos: int) -> int:
    return txt.count("\n", 0, pos) + 1


def scan_repository(root: Path | None = None) -> ScanResult:
    """Scan the repo for JSON access patterns. Read-only."""
    root = Path(root) if root else REPO_ROOT
    result = ScanResult()

    candidates: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        dp = Path(dirpath)
        if _should_exclude(dp, root):
            continue
        for fn in filenames:
            if fn.endswith(SCAN_EXTENSIONS):
                candidates.append(dp / fn)

    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        result.scanned_files += 1
        rel = path.relative_to(root).as_posix()

        # Constant definitions: NAME = ROOT / "x.json"
        for m in __import__("re").finditer(
            r'([A-Z][A-Z0-9_]+)\s*=\s*ROOT\s*/\s*"([^"]+\.json)"', text
        ):
            result.constant_map[m.group(1)] = m.group(2)

        for needle, kind in ACCESS_PATTERNS:
            start = 0
            while True:
                idx = text.find(needle, start)
                if idx == -1:
                    break
                line_no = _line_of(text, idx)
                line_start = text.rfind("\n", 0, idx) + 1
                line_end = text.find("\n", idx)
                if line_end == -1:
                    line_end = len(text)
                snippet = text[line_start:line_end].strip()
                symbol = None
                for cname, cfile in result.constant_map.items():
                    if cname in snippet:
                        symbol = cname
                        break
                result.sites.append(
                    AccessSite(rel, line_no, snippet[:160], kind, symbol)
                )
                start = idx + len(needle)

    return result


def root_json_inventory(root: Path | None = None) -> List[str]:
    """List root-level *.json files, excluding generated/artifact trees."""
    root = Path(root) if root else REPO_ROOT
    out = []
    for p in root.glob("*.json"):
        if p.is_file():
            out.append(p.name)
    return sorted(out)


def resolve_resource_for_json(
    filename: str,
    manifest: Dict[str, object],
    scan: ScanResult,
) -> Tuple[Optional[object], List[AccessSite]]:
    """Return (manifest_resource, access_sites) for a root JSON filename."""
    from .resource_manifest import classify_root_json

    resource = classify_root_json(filename, manifest)
    sites: List[AccessSite] = []
    for site in scan.sites:
        if site.symbol and manifest:
            for r in manifest.values():
                if r.legacy_file == filename and r.legacy_file:
                    pass
        # Match by constant name mapped to this file.
        for cname, cfile in scan.constant_map.items():
            if cfile == filename and site.symbol == cname:
                sites.append(site)
        # Also direct literal use.
        if filename in site.snippet:
            sites.append(site)
    return resource, sites


def build_inventory_report(
    root: Path | None = None,
    manifest: Dict[str, object] | None = None,
) -> dict:
    """Build a deterministic inventory dict (safe to JSON-serialize)."""
    from .resource_manifest import load_manifest

    root = Path(root) if root else REPO_ROOT
    manifest = manifest if manifest is not None else load_manifest()
    scan = scan_repository(root)
    root_jsons = root_json_inventory(root)

    files = []
    for filename in root_jsons:
        resource, sites = resolve_resource_for_json(filename, manifest, scan)
        writers = [f"{s.path}:{s.line}" for s in sites if s.kind in ("write", "read_or_write")]
        readers = [f"{s.path}:{s.line}" for s in sites if s.kind in ("read", "read_or_write")]
        files.append(
            {
                "file": filename,
                "resource": resource.resource if resource else None,
                "classification": resource.classification if resource else "unknown",
                "writers": writers,
                "readers": readers,
                "durable": resource.durable if resource else False,
                "target": resource.target if resource else "",
                "migration_action": resource.migration_action if resource else "",
            }
        )

    return {
        "scanned_files": scan.scanned_files,
        "root_json_count": len(root_jsons),
        "classified": sum(1 for f in files if f["classification"] != "unknown"),
        "unknown": sum(1 for f in files if f["classification"] == "unknown"),
        "constant_map_size": len(scan.constant_map),
        "access_sites": len(scan.sites),
        "files": files,
    }


def main() -> int:
    report = build_inventory_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
