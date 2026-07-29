"""Verify the Stage 2 V1 cryptographic evidence manifest.

Recomputes every recorded SHA-256 and confirms each artifact is present and
unchanged. Exits non-zero on any mismatch. This is the independent verification
anyone with the repo can run to confirm the V1 report derived from the exact
artifact set recorded in the evidence manifest.

Usage:
    PYTHONPATH= python tests/render_ab/verify_stage2_v1_evidence.py \
        --evidence-manifest .hermes/evidence/stage2-v1-evidence-manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-manifest", type=Path, required=True)
    parser.add_argument("--exec-bundle", type=Path, default=None,
                        help="optional: re-hash code files recorded in the "
                             "exec bundle and report drift (non-fatal)")
    args = parser.parse_args()

    em_path = args.evidence_manifest.resolve()
    if not em_path.exists():
        print(f"EVIDENCE_MANIFEST_MISSING: {em_path}")
        return 1
    em = json.loads(em_path.read_text(encoding="utf-8"))

    failures = []

    def check(rec: dict, label: str) -> None:
        full = (ROOT / rec["path"]).resolve()
        if not full.exists():
            failures.append(f"{label}: MISSING {rec['path']}")
            return
        if sha256(full) != rec["sha256"]:
            failures.append(f"{label}: SHA256 MISMATCH {rec['path']}")
        if full.stat().st_size != rec.get("bytes"):
            failures.append(f"{label}: SIZE MISMATCH {rec['path']}")

    check(em["artifacts"]["manifest"], "manifest")
    check(em["artifacts"]["approval"], "approval")
    check(em["artifacts"]["report"], "report")
    for rec in em["artifacts"]["execution_records"]:
        check(rec, "exec")
    for rec in em["artifacts"]["reviews"]:
        check(rec, "review")
    for rec in em["artifacts"]["provenance"]:
        check(rec, "provenance")
    for rec in em["artifacts"]["candidates"]:
        check(rec, "candidate")

    # recompute the bound manifest hash to confirm it still matches the field
    bound = sha256((ROOT / em["artifacts"]["manifest"]["path"]).resolve())
    if bound != em["bound_manifest_sha256"]:
        failures.append(f"BOUND_MANIFEST_HASH: recorded {em['bound_manifest_sha256']} != recomputed {bound}")

    # optional code-drift report against the exec bundle (non-fatal)
    code_drift = []
    if args.exec_bundle is not None:
        if not args.exec_bundle.exists():
            print(f"EXEC_BUNDLE_MISSING: {args.exec_bundle}")
            return 1
        bundle = json.loads(args.exec_bundle.read_text(encoding="utf-8"))
        for role, recorded in bundle.get("code_hashes", {}).items():
            # map role back to its source file via the bundle's recorded set
            rel = {
                "generator": "stage2_validation.py",
                "collector": "stage2_validation.py",
                "runner": "tests/render_ab/run_stage2_v1.py",
                "review_writer": "tests/render_ab/record_stage2_v1_review.py",
                "verifier": "tests/render_ab/verify_stage2_v1_evidence.py",
                "introspector": "tests/render_ab/introspect_stage2_v1_env.py",
                "evidence_builder": "tests/render_ab/build_stage2_v1_evidence_manifest.py",
                "review_sheet_builder": "tests/render_ab/build_stage2_v1_review_sheet.py",
            }.get(role)
            if rel is None:
                continue
            current = sha256((ROOT / rel).resolve())
            if current != recorded:
                code_drift.append(f"{role}: {rel} DRIFT recorded={recorded[:16]} current={current[:16] if current else None}")

    if failures:
        print("VERIFY_FAILED")
        for f in failures:
            print("  ", f)
        return 1

    print("VERIFY_OK")
    out = {
        "bound_manifest_sha256": em["bound_manifest_sha256"],
        "counts": em["counts"],
        "artifacts_checked": (
            1 + 1 + 1
            + len(em["artifacts"]["execution_records"])
            + len(em["artifacts"]["reviews"])
            + len(em["artifacts"]["provenance"])
            + len(em["artifacts"]["candidates"])
        ),
    }
    if code_drift:
        out["code_drift"] = code_drift
        print(json.dumps(out, indent=2))
        print("CODE_DRIFT_DETECTED (non-fatal): the code files have changed "
              "since the bundle was generated. Re-run build_stage2_v1_exec_bundle.py "
              "to refresh, or confirm the changes are unrelated to V1.")
    else:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
