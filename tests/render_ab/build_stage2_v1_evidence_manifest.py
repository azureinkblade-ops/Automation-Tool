"""Build a cryptographically anchored evidence manifest for the Stage 2 V1 study.

Records every artifact (manifest, approval, report, 24 execution records,
24 reviews, 24 provenance files, 24 candidates) with its SHA-256 digest so the
V1 report can be shown to derive from an exact, verifiable artifact set.

The generated manifest is consumed by verify_stage2_v1_evidence.py, which
recomputes every digest and confirms the bound manifest hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def entry(name: str, path: Path) -> dict:
    return {
        "id": name,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True,
                        help="frozen V1 manifest JSON")
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True,
                        help="dir containing stage2-v1-execution/*.json")
    parser.add_argument("--reviews-dir", type=Path, required=True)
    parser.add_argument("--candidates-dir", type=Path, required=True,
                        help="tests/render_ab/output/stage2_v1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    bound_hash = sha256(manifest_path)

    evidence_dir = args.evidence_dir.resolve()
    reviews_dir = args.reviews_dir.resolve()
    candidates_dir = args.candidates_dir.resolve()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ids = [c["case_id"] for c in manifest["cases"]]

    execution_records = []
    for cid in ids:
        p = evidence_dir / f"{cid}.json"
        execution_records.append(entry(cid, p))

    reviews = []
    for cid in ids:
        p = reviews_dir / f"{cid}.json"
        reviews.append(entry(cid, p))

    provenance = []
    for cid in ids:
        p = candidates_dir / cid / "provenance.json"
        provenance.append(entry(cid, p))

    candidates = []
    for cid in ids:
        p = candidates_dir / cid / "candidate.png"
        candidates.append(entry(cid, p))

    evidence = {
        "schema_version": 1,
        "suite": "stage2-v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "bound_manifest_sha256": bound_hash,
        "artifacts": {
            "manifest": entry("manifest", manifest_path),
            "approval": entry("approval", args.approval.resolve()),
            "report": entry("report", args.report.resolve()),
            "execution_records": execution_records,
            "reviews": reviews,
            "provenance": provenance,
            "candidates": candidates,
        },
        "counts": {
            "execution_records": len(execution_records),
            "reviews": len(reviews),
            "provenance": len(provenance),
            "candidates": len(candidates),
        },
        "verification_command": (
            "PYTHONPATH= python tests/render_ab/verify_stage2_v1_evidence.py "
            "--evidence-manifest .hermes/evidence/stage2-v1-evidence-manifest.json"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({
        "written": str(args.output),
        "bound_manifest_sha256": bound_hash,
        "counts": evidence["counts"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
