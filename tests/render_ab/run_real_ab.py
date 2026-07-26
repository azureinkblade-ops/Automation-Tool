"""Driver for the REAL rendered A/B through the application image workflow.

EXECUTION: run in the environment where the app's image pipeline is ready
(the local Stable Diffusion GPU runtime). Default engine = LOCAL STABLE
DIFFUSION (the app's MAIN image source) -> no API billing. Use --backend openai
only if local SD is unavailable; that path bills OpenAI and needs
ENABLE_EXTERNAL_AI=1 + OPENAI_API_KEY.

What this does (faithful to the directive):
  - captures the exact 3 legacy + 3 Director prompts from app.make_chapter_image_prompts
  - renders BOTH sets through the real app generation path into a sandbox
    (legacy/ and visual-director/)
  - records the REAL provider trace per image (model/LoRA/seed/size, or
    openai model/size/quality) via app.write_image_provider_trace, so we verify
    the engine that actually rendered (not a configured label)
  - writes manifest.json (prompts, traces, filenames, failures, timestamps) and
    report.md review sheet with the 7-criterion scoring table + gate
  - does NOT touch production metadata, approved image banks, or TikTok packs
    (the local-SD backend deliberately omits the rotation-state writes)

Local SD requirements (must hold in the runtime):
  torch/diffusers/transformers/PIL importable, local_image_generator.py present,
  an SDXL model on disk (local_stable_diffusion_status()['ready'] == True).

Scoring: this script writes the prompts/traces/report SKELETON. Fill the
criteria scores (1-5) per set + per-image Liang-recognizable flags, then run the
gate. The gate is computed by harness.evaluate_gate.
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
    ap.add_argument("--backend", choices=["local-sd", "openai"], default="local-sd")
    ap.add_argument("--scene-id", default="hp_liang_review")
    args = ap.parse_args()

    if args.backend == "openai":
        if not os.environ.get("ENABLE_EXTERNAL_AI") == "1":
            print("ERROR: --backend openai requires ENABLE_EXTERNAL_AI=1 (cost-bearing OpenAI run).")
            sys.exit(2)
        if not os.environ.get("OPENAI_API_KEY"):
            print("ERROR: --backend openai requires OPENAI_API_KEY (bills a real key).")
            sys.exit(2)
        backend = H.OpenAIAppBackend(app_module=appmod, size="1024x1536", quality="medium")
    else:
        # Local SD: the app's main source, runs on local GPU, no API billing.
        st = appmod.local_stable_diffusion_status()
        if not st.get("ready"):
            missing = [n for n, r in (st.get("dependencies") or {}).items() if not r]
            print(f"ERROR: local Stable Diffusion not ready (missing: {', '.join(missing) or 'generator'}). "
                  f"Run in the SD GPU runtime, or use --backend openai with ENABLE_EXTERNAL_AI=1.")
            sys.exit(2)
        backend = H.LocalSDAppBackend(app_module=appmod, orientation="vertical", quality_mode="")

    title, chapter, phrases, novel = SCENE
    prompts = H.capture_prompts(title, chapter, phrases, novel, appmod)
    out_root = Path(args.out)
    ab = H.run_ab(args.scene_id, prompts["legacy"], prompts["director"], backend, out_root)

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
        "engine": args.backend,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "control": "single variable = prompt; same engine/model/LoRA/size/quality for both sets",
        "prompts": prompts,
        "ab": ab,
        "failures": failures,
    }
    H.write_manifest(out_root / "manifest.json", manifest)
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

    print(f"Engine: {args.backend}")
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
    print("Next: score each set (1-5) + per-image Liang-recognizable, then compute the gate.")
    print("NOTE: provider trace recorded per image via app.write_image_provider_trace (real engine, not label).")


if __name__ == "__main__":
    main()
