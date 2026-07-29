"""Execute the frozen Stage 2 V1 study through the quarantined service boundary.

Dry-run is CPU-only. GPU execution requires an explicit manifest-bound approval
record and the --execute switch.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from local_object_refinement_backend import LocalSDXLInpaintBackend
from object_refinement import ObjectRefinementService, RefinementRequest
from stage2_validation import preflight_manifest

APPROVAL_SCOPE = "stage2-v1-gpu-execution"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(base: Path, raw: str | None) -> Path | None:
    if raw is None:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base / path).resolve()


def validate_approval(
    approval_path: Path,
    manifest_path: Path,
) -> Mapping[str, Any]:
    if not approval_path.exists():
        raise ValueError("explicit GPU approval record is missing")
    payload = json.loads(approval_path.read_text(encoding="utf-8"))
    if payload.get("approved") is not True:
        raise ValueError("GPU approval record is not approved")
    if payload.get("scope") != APPROVAL_SCOPE:
        raise ValueError("GPU approval scope mismatch")
    if payload.get("manifest_sha256") != sha256(manifest_path):
        raise ValueError("GPU approval manifest hash mismatch")
    if not str(payload.get("approval_text", "")).strip():
        raise ValueError("GPU approval text is missing")
    if not str(payload.get("approved_at", "")).strip():
        raise ValueError("GPU approval timestamp is missing")
    return payload


def terminal_record_path(base: Path, raw: Mapping[str, Any]) -> Path:
    path = resolve(base, raw.get("execution_record_path"))
    if path is None:
        raise ValueError(f"{raw.get('case_id')}: execution_record_path missing from manifest")
    return path


def run_case(manifest_path: Path, raw: Mapping[str, Any]) -> Mapping[str, Any]:
    base = manifest_path.parent
    case_id = str(raw["case_id"])
    source = resolve(base, raw["source_path"])
    mask = resolve(base, raw["mask_path"])
    guide = resolve(base, raw.get("guide_path"))
    record_path = terminal_record_path(base, raw)
    work_dir = (ROOT / "tests/render_ab/output/stage2_v1" / case_id).resolve()
    config = dict(raw["generation_config"])
    started_at = datetime.now(timezone.utc).astimezone().isoformat()
    started = time.perf_counter()
    record: dict[str, Any] = {
        "schema_version": 1,
        "case_id": case_id,
        "status": "running",
        "started_at": started_at,
        "attempts": 1,
        "second_refinement_attempted": False,
        "manual_intervention_cycles": 0,
        "automatic_publish_events": 0,
        "manifest_sha256": sha256(manifest_path),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    try:
        backend = LocalSDXLInpaintBackend(
            python_executable=str(ROOT / ".venv-gpu/Scripts/python.exe"),
            script_path=ROOT / "local_object_refiner.py",
            model_path=ROOT / str(config["model"]),
            lora_path=ROOT / str(config["lora"]),
            seed=int(config["seed"]),
            strength=float(config["strength"]),
            steps=int(config["steps"]),
            guidance_scale=float(config["guidance_scale"]),
            lora_scale=float(config["lora_scale"]),
            timeout_seconds=900,
        )
        result = ObjectRefinementService(backend=backend).refine(
            source,
            RefinementRequest(
                object_type=str(raw["object_type"]),
                target_region=str(raw["target_region"]),
                prompt=str(raw["prompt"]),
                mask_path=mask,
                guide_path=guide,
            ),
            work_dir,
        )
        if result.status != "pending_review" or result.output_path != source:
            raise RuntimeError(
                "quarantine contract violated: expected pending_review with source effective"
            )
        record.update({
            "status": "completed",
            "generation_seconds": time.perf_counter() - started,
            "completed_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "candidate_path": str(result.candidate_path),
            "pending_provenance_path": str(result.provenance_path),
            "diff_path": str(result.diff_path),
            "effective_output_path": str(result.output_path),
        })
    except Exception as exc:
        record.update({
            "status": "backend_failed",
            "generation_seconds": time.perf_counter() - started,
            "completed_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        })
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--approval-record", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    preflight = preflight_manifest(manifest_path)
    if not preflight.ok:
        raise SystemExit("preflight failed: " + "; ".join(preflight.errors))
    for raw in manifest["cases"]:
        terminal_record_path(manifest_path.parent, raw)
    if not args.execute:
        print(json.dumps({
            "status": "DRY_RUN_READY_AWAITING_EXPLICIT_GPU_APPROVAL",
            "case_count": len(manifest["cases"]),
            "manifest_sha256": sha256(manifest_path),
        }))
        return 0
    if args.approval_record is None:
        raise SystemExit("--approval-record is required with --execute")
    validate_approval(args.approval_record.resolve(), manifest_path)

    os.environ["VISUAL_OBJECT_REFINEMENT_ENABLED"] = "1"
    records = []
    for raw in manifest["cases"]:
        record_path = terminal_record_path(manifest_path.parent, raw)
        if args.resume and record_path.exists():
            existing = json.loads(record_path.read_text(encoding="utf-8"))
            if existing.get("status") in {"completed", "backend_failed"}:
                records.append(existing)
                print(json.dumps({"case_id": raw["case_id"], "status": "resume_skip"}), flush=True)
                continue
        record = run_case(manifest_path, raw)
        records.append(record)
        print(json.dumps({
            "case_id": record["case_id"],
            "status": record["status"],
            "generation_seconds": record.get("generation_seconds"),
        }), flush=True)

    completed = sum(1 for row in records if row.get("status") == "completed")
    failed = sum(1 for row in records if row.get("status") == "backend_failed")
    print(json.dumps({
        "status": "V1_GENERATION_ATTEMPTS_COMPLETE",
        "attempted": len(records),
        "completed": completed,
        "backend_failed": failed,
        "candidates_quarantined": completed,
        "automatic_publish_events": 0,
    }))
    return 0 if len(records) == len(manifest["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
