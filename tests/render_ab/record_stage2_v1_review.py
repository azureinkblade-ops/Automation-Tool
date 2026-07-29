"""Structured human review recorder for Stage 2 V1.

Loads the frozen manifest and each quarantined candidate, renders a
side-by-side review image, and records the reviewer's structured verdict
to the per-case review path declared in the manifest. This tool only
WRITES review records; it never publishes, finalizes, or modifies the
source candidate.

The actual visual judgement is performed by the reviewer (Hermes vision
pass) case by case; this module persists the decision and enforces the
required field schema so the schema-v3 report can aggregate honestly.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

GATES = (
    "object_recognizable",
    "placement_attachment_valid",
    "no_duplicate_floating_substitution",
    "identity_preserved",
    "pose_preserved",
    "anatomy_preserved",
    "clothing_composition_preserved",
)

REVIEW_CATEGORIES = {
    "object_unrecognizable",
    "floating_object",
    "duplicate_object",
    "substituted_object",
    "misplaced_attachment",
    "identity_regression",
    "pose_regression",
    "anatomy_corruption",
    "hands_corruption",
    "clothing_composition_regression",
    "outside_mask_leakage",
    "no_change",
    "backend_failure",
}


def resolve(base: Path, raw: str | None) -> Path | None:
    if raw is None:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base / path).resolve()


def record_review(
    manifest_path: Path,
    case_id: str,
    overall_accept: bool,
    gates: dict[str, bool],
    rejection_categories: list[str],
    reviewer_notes: str,
    preparation_seconds: float | None,
    review_seconds: float | None,
    manual_intervention_cycles: int | None,
) -> Path:
    manifest_path = manifest_path.resolve()
    base = manifest_path.parent
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    case = next((c for c in payload["cases"] if c["case_id"] == case_id), None)
    if case is None:
        raise ValueError(f"{case_id}: not found in manifest")

    missing = [g for g in GATES if g not in gates]
    if missing:
        raise ValueError(f"{case_id}: missing gate fields: {missing}")
    unknown = set(rejection_categories) - REVIEW_CATEGORIES
    if unknown:
        raise ValueError(f"{case_id}: unknown rejection categories: {sorted(unknown)}")

    review_path = resolve(base, case["review_path"])
    if review_path is None:
        raise ValueError(f"{case_id}: review_path missing from manifest")
    review_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "schema_version": 1,
        "case_id": case_id,
        "reviewed_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "reviewer": "hermes_vision_pass",
        "overall_accept": bool(overall_accept),
        "gates": {gate: bool(gates[gate]) for gate in GATES},
        "rejection_categories": list(rejection_categories),
        "reviewer_notes": reviewer_notes,
        "preparation_seconds": preparation_seconds,
        "review_seconds": review_seconds,
        "manual_intervention_cycles": manual_intervention_cycles,
        "manifest_sha256": None,  # filled by caller if desired
    }
    review_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return review_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--accept", action="store_true")
    parser.add_argument("--reject", action="store_true")
    parser.add_argument(
        "--gate", action="append", default=[],
        metavar="NAME=1|0",
        help="one of: " + ",".join(GATES),
    )
    parser.add_argument(
        "--reject-category", action="append", default=[],
        metavar="CATEGORY",
        help="one of: " + ",".join(sorted(REVIEW_CATEGORIES)),
    )
    parser.add_argument("--notes", default="")
    parser.add_argument("--preparation-seconds", type=float, default=None)
    parser.add_argument("--review-seconds", type=float, default=None)
    parser.add_argument("--manual-intervention-cycles", type=int, default=None)
    args = parser.parse_args()

    if args.accept and args.reject:
        raise SystemExit("use exactly one of --accept / --reject")
    if not (args.accept or args.reject):
        raise SystemExit("use exactly one of --accept / --reject")

    gates: dict[str, bool] = {}
    for item in args.gate:
        if "=" not in item:
            raise SystemExit(f"bad --gate {item}; expected NAME=1|0")
        name, value = item.split("=", 1)
        if name not in GATES:
            raise SystemExit(f"unknown gate {name}")
        gates[name] = value.strip() in {"1", "true", "yes"}

    path = record_review(
        args.manifest,
        args.case_id,
        overall_accept=args.accept,
        gates=gates,
        rejection_categories=args.reject_category,
        reviewer_notes=args.notes,
        preparation_seconds=args.preparation_seconds,
        review_seconds=args.review_seconds,
        manual_intervention_cycles=args.manual_intervention_cycles,
    )
    print(json.dumps({"case_id": args.case_id, "review_path": str(path), "written": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
