"""Blocking preflight and frozen-hash report for Stage 2 V1."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from stage2_validation import preflight_manifest


EXPECTED_ALLOCATION = {
    "sheathed_sword": 6,
    "drawn_sword": 4,
    "scabbard_weapon_repair": 4,
    "non_weapon_prop": 4,
    "hand_repair": 3,
    "clothing_defect": 3,
}
BANNED_SOURCE_TERMS = (
    "deep-tiktok", "deep_tiktok", "reel", "stock", "pixabay", "lora-training",
    "eval-grid", "novel-promo-card", "weekly", "thumbnail",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(base: Path, raw: str | None) -> Path | None:
    if raw is None:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    base = args.manifest.parent
    report = preflight_manifest(args.manifest)
    errors = list(report.errors)
    class_counts = Counter()
    novel_counts = Counter()
    case_rows = []
    for raw in manifest.get("cases", []):
        case_id = str(raw["case_id"])
        class_counts[str(raw["strata"]["object_class"])] += 1
        novel_counts[str(raw["strata"].get("novel", "UNDECLARED"))] += 1
        source = resolve(base, raw.get("source_path"))
        mask = resolve(base, raw.get("mask_path"))
        guide = resolve(base, raw.get("guide_path"))
        source_string = str(source).replace("\\", "/").lower()
        for term in BANNED_SOURCE_TERMS:
            if term in source_string:
                errors.append(f"{case_id}: banned source path term: {term}")
        observed_hashes = {
            "source_sha256": sha256(source),
            "mask_sha256": sha256(mask),
            "guide_sha256": sha256(guide) if guide else None,
        }
        if observed_hashes != raw.get("fixture_hashes"):
            errors.append(f"{case_id}: stored fixture hashes do not match files")
        case_rows.append({
            "case_id": case_id,
            "source_path": str(source),
            "mask_path": str(mask),
            "guide_path": str(guide) if guide else None,
            **observed_hashes,
        })
    if len(manifest.get("cases", [])) != 24:
        errors.append(f"expected 24 cases, got {len(manifest.get('cases', []))}")
    if dict(class_counts) != EXPECTED_ALLOCATION:
        errors.append(f"allocation mismatch: {dict(class_counts)}")
    if len({row["source_sha256"] for row in case_rows}) != len(case_rows):
        errors.append("source hashes are not unique")

    payload = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "manifest_path": str(args.manifest.resolve()),
        "manifest_sha256": sha256(args.manifest),
        "status": "PREFLIGHT_PASS" if report.ok and not errors else "PREFLIGHT_FAIL",
        "case_count": len(case_rows),
        "unique_source_hashes": len({row["source_sha256"] for row in case_rows}),
        "object_class_counts": dict(class_counts),
        "novel_counts": dict(novel_counts),
        "harness_errors": list(report.errors),
        "all_errors": errors,
        "cases": case_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "case_count", "unique_source_hashes", "object_class_counts", "novel_counts", "all_errors")}))
    return 0 if payload["status"] == "PREFLIGHT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
