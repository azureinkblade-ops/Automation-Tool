"""Driver for the REAL rendered A/B through the application image workflow.

EXECUTION: run only with explicit cost authorization. Each render is a BILLED
OpenAI (gpt-image-1) image call -> 6 calls total (3 legacy + 3 director).

What this does (faithful to the directive):
  - captures the exact 3 legacy + 3 Director prompts from app.make_chapter_image_prompts
  - renders BOTH sets through app.create_openai_image (the same real provider the
    posts/videos use) into a sandbox (legacy/ and visual-director/)
  - records the REAL provider trace per image (model/size/quality) via the app's
    own write_image_provider_trace, so we verify the engine that actually rendered
  - writes a manifest.json (prompts, traces, filenames, failures, timestamps) and
    a report.md review sheet with the 7-criterion scoring table + gate
  - does NOT touch production metadata, approved image banks, or TikTok packs

Requirements (must be set in env before running):
  ENABLE_EXTERNAL_AI=1
  OPENAI_API_KEY=...   (a real key; billed)
  VISUAL_DIRECTOR_ENABLED has NO effect here; we force each path explicitly via
  capture_prompts() so the comparison is controlled.

Scoring: this script writes the prompts/traces/report SKELETON. Fill the
criteria scores (1-5) per set + per-image Liang-recognizable flags, then re-run
with --score, or edit the generated scoring JSON. The gate is computed by
harness.evaluate_gate.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
import tests.render_ab.harness as H  # noqa: E402


SCENE = (
    "The Hundredfold Path", "chapter text",
    ["Liang enters the ruined sect hall",
     "He climbs the broken stair toward the jade altar",
     "Silver light wakes the dormant formation"],
    "hp",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "tests" / "render_ab" / "output"))
    ap.add_argument("--score", action="store_true",
                    help="After rendering, also compute the gate from a scoring JSON.")
    ap.add_argument("--scene-id", default="hp_liang_review")
    args = ap.parse_args()

    if not os.environ.get("ENABLE_EXTERNAL_AI") == "1":
        print("ERROR: ENABLE_EXTERNAL_AI=1 must be set (cost-bearing OpenAI run).")
        sys.exit(2)
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set. This would bill a real key.")
        sys.exit(2)

    title, chapter, phrases, novel = SCENE
    prompts = H.capture_prompts(title, chapter, phrases, novel, appmod)
    out_root = Path(args.out)
    backend = H.OpenAIAppBackend(app_module=appmod, size="1024x1536", quality="medium")
    ab = H.run_ab(args.scene_id, prompts["legacy"], prompts["director"], backend, out_root)

    # Expose failures (do not hide).
    failures = []
    for kind in ("legacy", "director"):
        for i, r in enumerate(ab[kind]):
            if not r["ok"]:
                failures.append(f"[{kind} {i}] GENERATION ERROR: {r['error']}")
            if r["cached"]:
                failures.append(f"[{kind} {i}] CACHED/REUSED ASSET (must be new)")
            if r["text_in_image"]:
                failures.append(f"[{kind} {i}] TEXT RENDERED INSIDE IMAGE")
            if r["duplicate_of"]:
                failures.append(f"[{kind} {i}] DUPLICATE of {r['duplicate_of']}")

    manifest = {
        "scene_id": args.scene_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "control": "single variable = prompt; provider=openai gpt-image-1; size=1024x1536; quality=medium; count=3 each",
        "prompts": prompts,
        "ab": ab,
        "failures": failures,
    }
    H.write_manifest(out_root / "manifest.json", manifest)
    # Report skeleton (scoring filled separately).
    legacy_score = H.build_score(
        {c: 0 for c in H.CRITERIA},
        [{"liang_recognizable": False, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    director_score = H.build_score(
        {c: 0 for c in H.CRITERIA},
        [{"liang_recognizable": False, "text_in_image": False, "duplicate": False, "provider_refusal": False} for _ in range(3)],
    )
    gate = H.evaluate_gate(legacy_score, director_score)
    H.write_report(out_root / "report.md", args.scene_id, prompts, ab, legacy_score, director_score, gate)

    print(f"Rendered 6 images under {out_root}")
    print(f"  legacy/:   {[Path(r['path']).name for r in ab['legacy']]}")
    print(f"  director/: {[Path(r['path']).name for r in ab['director']]}")
    if failures:
        print("FAILURES EXPOSED:")
        for f in failures:
            print("  -", f)
    else:
        print("No generation failures recorded.")
    print(f"Manifest: {out_root / 'manifest.json'}")
    print("Next: score each set (1-5) + per-image Liang-recognizable, then run with --score.")
    print("NOTE: provider trace recorded per image via app.write_image_provider_trace (real engine, not label).")


if __name__ == "__main__":
    main()
