"""Stage 2 V1 reproducible-execution bundle (chain-of-custody).

Extends the artifact-integrity manifest with the execution-environment context
needed to reproduce (or audit) the V1 run: git HEAD + working-tree diff hash,
hashes of the generator / collector / runner / review-writer / verifier source
files, exact command lines, python + package versions, GPU + model + LoRA file
hashes, run start/completion timestamps (taken from the execution records), and
a parent hash over the canonicalized bundle itself.

This does NOT by itself prove the report code was the code that produced the
report, or that reviews were produced by the claimed process. It records the
environment and code identities so a reviewer can check them. The earlier
artifact-integrity manifest remains the canonical "did these bytes change"
anchor; this bundle sits alongside it.

Usage:
    PYTHONPATH= python tests/render_ab/build_stage2_v1_exec_bundle.py \
        --evidence-manifest .hermes/evidence/stage2-v1-evidence-manifest.json \
        --manifest .hermes/evidence/stage2-validation-v1-manifest.json \
        --approval .hermes/evidence/stage2-v1-gpu-approval.json \
        --report .hermes/evidence/stage2-validation-v1-report.json \
        --env-json <introspect output> \
        --output .hermes/evidence/stage2-v1-exec-bundle.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-manifest", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--env-json", type=Path, required=True,
                        help="output of introspect_stage2_v1_env.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    approval_path = args.approval.resolve()
    report_path = args.report.resolve()
    env = json.loads(args.env_json.read_text(encoding="utf-8"))

    # code identities
    code_files = {
        "generator": "stage2_validation.py",
        "collector": "stage2_validation.py",
        "runner": "tests/render_ab/run_stage2_v1.py",
        "review_writer": "tests/render_ab/record_stage2_v1_review.py",
        "verifier": "tests/render_ab/verify_stage2_v1_evidence.py",
        "introspector": "tests/render_ab/introspect_stage2_v1_env.py",
        "evidence_builder": "tests/render_ab/build_stage2_v1_evidence_manifest.py",
        "review_sheet_builder": "tests/render_ab/build_stage2_v1_review_sheet.py",
    }
    code_hashes = {
        role: sha256(ROOT / rel) for role, rel in code_files.items()
    }

    # exact command lines that produced / verify the artifacts
    commands = {
        "generate": (
            ".venv-gpu/Scripts/python.exe tests/render_ab/run_stage2_v1.py "
            "--manifest .hermes/evidence/stage2-validation-v1-manifest.json "
            "--approval-record .hermes/evidence/stage2-v1-gpu-approval.json "
            "--execute --resume"
        ),
        "report": (
            "PYTHONPATH= .venv-gpu/Scripts/python.exe stage2_validation.py "
            "--manifest .hermes/evidence/stage2-validation-v1-manifest.json "
            "--output .hermes/evidence/stage2-validation-v1-report.json"
        ),
        "review_writer": (
            "tests/render_ab/record_stage2_v1_review.py --manifest <manifest> "
            "--case-id <id> --accept --gate <gate>=1 ..."
        ),
        "verify": (
            "PYTHONPATH= python tests/render_ab/verify_stage2_v1_evidence.py "
            "--evidence-manifest .hermes/evidence/stage2-v1-evidence-manifest.json"
        ),
    }

    # run timestamps from execution records
    exec_dir = (args.evidence_manifest.parent / "stage2-v1-execution")
    starts, completes = [], []
    for p in sorted(exec_dir.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("started_at"):
            starts.append(rec["started_at"])
        if rec.get("completed_at"):
            completes.append(rec["completed_at"])

    bundle = {
        "schema_version": 1,
        "suite": "stage2-v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "git": {
            "head": env.get("git_head"),
            "dirty_tree_diff_sha256": env.get("git_dirty_tree_diff_sha256"),
            "status_porcelain_entries": env.get("git_status_porcelain_len"),
            "note": (
                "Stage 2 V1 work is uncommitted Slice B0 ControlNet diff on top "
                "of HEAD 4e10045 (app.py, local_image_generator.py, tests/render_"
                "ab/harness.py, tests/render_ab/run_real_ab.py). The dirty-tree "
                "diff hash above covers only those four production-path files."
            ),
        },
        "interpreter": env.get("interpreter"),
        "python_version": env.get("python_version"),
        "packages": env.get("packages"),
        "gpu": {
            "name": env.get("gpu_name"),
            "cuda_available": env.get("cuda_available"),
            "note": env.get("gpu_note"),
        },
        "model_files": {
            "sdxl_base_sha256": env.get("model_files", {}).get("sdxl_base"),
            "lora_azink_main_sha256": env.get("model_files", {}).get("lora_azink_main"),
        },
        "code_hashes": code_hashes,
        "commands": commands,
        "run_window": {
            "earliest_started_at": min(starts) if starts else None,
            "latest_completed_at": max(completes) if completes else None,
        },
        "links": {
            "evidence_manifest": str(args.evidence_manifest.resolve().relative_to(ROOT)).replace("\\", "/"),
            "frozen_manifest": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
            "approval": str(approval_path.relative_to(ROOT)).replace("\\", "/"),
            "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        },
        "limitations": (
            "This bundle records environment and code identities at bundle-"
            "generation time. It does NOT cryptographically prove that the "
            "report-generation code was the code that produced the report, nor "
            "that the reviews were produced by the claimed visual-process. It "
            "enables a reviewer to check those identities against the running "
            "system; it is not a proof of process."
        ),
    }

    # parent hash over a canonicalized, sorted serialization (excluding this field)
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    bundle["parent_hash_over_canonical_bundle"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(json.dumps({
        "written": str(args.output),
        "parent_hash": bundle["parent_hash_over_canonical_bundle"],
        "git_head": bundle["git"]["head"],
        "code_identities_recorded": len(code_hashes),
        "run_window": bundle["run_window"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
