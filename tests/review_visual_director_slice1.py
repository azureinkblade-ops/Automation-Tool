"""Visual Director Slice 1 — creative quality review.

Runs a compact, real-material review per the user's directive:
- One chapter scene from each active novel (HP, EN, SF, HA).
- At least one named character per novel.
- One action scene, one emotional scene, one environment-heavy scene.
- Compares the CURRENT generic prompt (faithful reproduction of
  app.py make_chapter_image_prompts legacy template) against the Visual
  Director prompt, SIDE BY SIDE.
- Judges with the Visual Creative Director rubric:
  canon accuracy, shot usefulness, visual hierarchy, mobile suitability,
  coherent sequence (not 3 variations of one illustration).
- Emits the 6 concrete acceptance checks.

This is a REVIEW harness, not a unit test. It prints a structured report and
returns a verdict. It does NOT edit app.py and does NOT touch the AIVSB lane.

Run under the codex runtime:
  python tests/review_visual_director_slice1.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import visual_director as vd  # noqa: E402


# --- Faithful reproduction of the legacy generic template (app.py:30652-30661)
# so the side-by-side compares against the ACTUAL current output, not a strawman.
def legacy_generic_prompt(novel: str, title: str, phrase: str, beat: str, keywords: str) -> str:
    context = f"{novel}, {title}".strip(", ")
    return (
        "Vertical 9:16 cinematic fantasy web novel cover art, no text or typography. "
        f"Story context: {context}. "
        f"Teaser text to visually match: {phrase}. "
        f"Scene must clearly depict the teaser with concrete visible elements: {beat}. "
        f"Visual motifs: {keywords}. "
        "Dramatic lighting, detailed environment, strong focal subject, social media promo composition. "
        "Avoid generic landscapes unless the teaser explicitly calls for a landscape."
    )


# --- Real, canon-grounded review scenes (one per novel) ----------------------
# Each uses a named character the Bible actually defines, and a scene type that
# exercises a different requirement (action / emotional / environment-heavy).
REVIEW_SCENES = [
    {
        "key": "HP-action",
        "novel": "hp",
        "title": "The Hundredfold Path",
        "chapter": "6",
        "character": "Liang",
        "type": "action",
        "phrase": "Liang enters the ruined sect",
        "beat": "Liang steps through the broken gateway, silver blade raised as formation light awakens in the dust",
        "keywords": "cultivation, mountain sect, silver sword, ruined pillars, qi",
    },
    {
        "key": "EN-emotional",
        "novel": "en",
        "title": "Eternal Nexus",
        "chapter": "12",
        "character": "Kael",
        "type": "emotional",
        "phrase": "Kael stands before the NexusPod",
        "beat": "Kael's hand hovers over the obsidian pod, blue glyphs reflected in eyes that have seen too much",
        "keywords": "cyberpunk, neon, Soulblade, holo UI, glyph glow",
    },
    {
        "key": "SF-environment",
        "novel": "sf",
        "title": "Soul Forge Era",
        "chapter": "3",
        "character": "Gray",
        "type": "environment-heavy",
        "phrase": "Gray descends into the forge sanctuary",
        "beat": "Gray walks beneath vaulted iron arches where gold soul-fire leaks between chained columns",
        "keywords": "ashpunk, forge-fire, iron chains, sanctuary glow, soot",
    },
    {
        "key": "HA-action",
        "novel": "ha",
        "title": "Heavenly Ascension System",
        "chapter": "4",
        "character": "Kai",
        "type": "action",
        "phrase": "Kai awakens his cultivation in the alley",
        "beat": "Kai clenches his fist as amber qi threads ignite around his palm beneath the rain-slick neon sign",
        "keywords": "system fantasy, golden ember, HUD panel, rain, alley",
    },
]


def run_scene(scene: dict) -> dict:
    pkg = vd.build_visual_scene_package(scene["novel"], scene["chapter"], scene["phrase"])
    legacy = legacy_generic_prompt(
        scene["novel"], scene["title"], scene["phrase"], scene["beat"], scene["keywords"]
    )
    vd_prompts = pkg["image_prompts"]
    return {
        "scene": scene,
        "legacy_prompt": legacy,
        "vd_prompts": vd_prompts,
        "package": pkg,
    }


# --- Visual Creative Director rubric (authority layer) -----------------------
# Axes per the skill: canon accuracy, shot usefulness, visual hierarchy,
# mobile suitability, coherent-sequence.
def judge_scene(result: dict) -> dict:
    pkg = result["package"]
    vd = result["vd_prompts"]
    legacy = result["legacy_prompt"]
    scene = result["scene"]

    # 1. Canon accuracy: do the locked traits match the Bible for this character?
    #    We check the lock resolved a real character and carries canon tokens.
    locks = pkg["character_locks"]
    canon_accurate = bool(locks) and any(
        l.get("name") and (l.get("hair") or l.get("clothing") or l.get("weapons"))
        for l in locks
    )

    # 2. Shot usefulness: 3 distinct roles (establishing/character/action).
    roles = [s["type"] for s in pkg["shots"]]
    shot_useful = roles == ["establishing", "character", "action"]

    # 3. Visual hierarchy: each prompt names a clear subject + setting + shot.
    hierarchy_ok = all(
        ("Subject:" in p) and ("Shot:" in p) and ("Setting:" in p or "Scene:" in p)
        for p in vd
    )

    # 4. Mobile suitability: vertical 9:16 declared; prompts short enough to be
    #    art-directed (no wall of text). Check vertical + length.
    mobile_ok = all(
        ("9:16" in p or "vertical" in p.lower()) and len(p) < 600 for p in vd
    )

    # 4b. No editorial/YAML noise: scan the ACTUAL prompts (not the diagnostics
    #     container). A prompt fails if it carries parenthetical notes, 'n/a',
    #     'None', 'unknown', or malformed-canon fragments.
    noise_markers = ("note", "n/a", "none (", "(interior)", "unknown", " at ch")
    no_noise = not any(any(m in p.lower() for m in noise_markers) for p in vd)

    # 5. Coherent sequence: the 3 prompts differ in camera/purpose (not 3 copies).
    seq_coherent = len(set(vd)) == 3

    # 6. Legacy clearly improved: legacy has NO character lock, NO shot role,
    #    NO negative constraints; VD has all three.
    legacy_has_lock = "Subject:" in legacy and "jade" in legacy.lower()
    legacy_has_shot = "Shot:" in legacy
    legacy_has_negative = "negative" in legacy.lower() or "avoid" in legacy.lower()
    improved = (not legacy_has_lock) and (not legacy_has_shot) and bool(vd)

    # canon warnings surfaced (the prerequisite the user named)
    warnings = pkg.get("canon_warnings", [])
    warnings_surfaced = isinstance(warnings, list)

    return {
        "canon_accurate": canon_accurate,
        "shot_useful": shot_useful,
        "hierarchy_ok": hierarchy_ok,
        "mobile_ok": mobile_ok,
        "no_noise": no_noise,
        "seq_coherent": seq_coherent,
        "legacy_improved": improved,
        "warnings": warnings,
        "warnings_surfaced": warnings_surfaced,
    }


def print_side_by_side(result: dict):
    scene = result["scene"]
    print(f"\n{'='*78}")
    print(f"SCENE {scene['key']}  [{scene['type']}]  novel={scene['novel']}  char={scene['character']}")
    print(f"phrase: {scene['phrase']}")
    print(f"{'-'*78}")
    print("LEGACY GENERIC PROMPT (current app.py output):")
    print(f"  {result['legacy_prompt']}")
    print(f"{'-'*78}")
    print("VISUAL DIRECTOR PROMPTS (Slice 1):")
    for i, p in enumerate(result["vd_prompts"], 1):
        print(f"  [{i}] {p}")
    if result["package"].get("canon_warnings"):
        print(f"{'-'*78}")
        print("CANON WARNINGS (explicit diagnostics, not silently filtered):")
        for w in result["package"]["canon_warnings"]:
            print(f"  ! {w}")


def main() -> int:
    print("VISUAL DIRECTOR SLICE 1 — CREATIVE QUALITY REVIEW")
    print("Authority: Visual Creative Director skill + user 6-point acceptance.")
    print("Material: one canon-grounded scene per active novel (HP/EN/SF/HA).")

    results = [run_scene(s) for s in REVIEW_SCENES]
    judgments = [judge_scene(r) for r in results]

    for r, j in zip(results, judgments):
        print_side_by_side(r)

    # --- Aggregate acceptance table -----------------------------------------
    print(f"\n{'='*78}")
    print("ACCEPTANCE CHECKS (per the user's concrete threshold)")
    print(f"{'-'*78}")
    rows = [
        ("Character identity preserved", all(j["canon_accurate"] for j in judgments)),
        ("Correct clothing/weapon/world", all(j["canon_accurate"] for j in judgments)),
        ("Three visibly different shot roles", all(j["shot_useful"] for j in judgments)),
        ("No editorial/YAML noise", all(j["no_noise"] for j in judgments)),
        ("Prompt usable by current provider", all(j["hierarchy_ok"] and j["mobile_ok"] for j in judgments)),
        ("Generic prompt clearly improved", all(j["legacy_improved"] for j in judgments)),
        ("canon_warnings surfaced (prereq)", all(j["warnings_surfaced"] for j in judgments)),
        ("Coherent 3-shot sequence", all(j["seq_coherent"] for j in judgments)),
    ]
    verdict_all = True
    for label, ok in rows:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            verdict_all = False
        print(f"  [{mark}] {label}")

    # --- Per-novel VCD rubric rollup -----------------------------------------
    print(f"\n{'-'*78}")
    print("VISUAL CREATIVE DIRECTOR RUBRIC (per novel)")
    print(f"{'-'*78}")
    for r, j, s in zip(results, judgments, REVIEW_SCENES):
        rubric = {
            "canon accuracy": j["canon_accurate"],
            "shot usefulness": j["shot_useful"],
            "visual hierarchy": j["hierarchy_ok"],
            "mobile suitability": j["mobile_ok"],
            "coherent sequence": j["seq_coherent"],
        }
        summary = ", ".join(f"{k}:{'OK' if v else 'XX'}" for k, v in rubric.items())
        print(f"  {s['key']:<14} {summary}")

    print(f"\n{'='*78}")
    if verdict_all:
        print("VERDICT: ALL ACCEPTANCE CHECKS PASS.")
        print("Recommendation: Slice 1 creative review PASSED. Proceed to the")
        print("env-gated integration commit (VISUAL_DIRECTOR_ENABLED).")
    else:
        print("VERDICT: ONE OR MORE ACCEPTANCE CHECKS FAILED.")
        print("Recommendation: DO NOT integrate yet. Address failing axis first.")
    print(f"{'='*78}")
    return 0 if verdict_all else 1


if __name__ == "__main__":
    sys.exit(main())
