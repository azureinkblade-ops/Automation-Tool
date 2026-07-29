# Visual Director Slice 1 — Creative Quality Review (authorization gate)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commits: `93b9241` (Slice 1 builder + tests) + `PARENT` (this review commit, run `git rev-parse --short HEAD`).
Lane owns app.py but NO app.py change in either commit.

## What was reviewed
Per the explicit directive, a compact creative-quality review using REAL canon-
grounded material (not synthetic):
- One chapter scene from each active novel: HP, EN, SF, HA.
- A named character per novel: Liang, Kael, Gray, Kai.
- Scene types: HP=action, EN=emotional, SF=environment-heavy, HA=action
  (covers action + emotional + environment-heavy as required).
- Each scene compared SIDE BY SIDE against the CURRENT legacy generic prompt
  (faithful reproduction of app.py make_chapter_image_prompts, lines 30652-30661)
  and the Visual Director prompt.

## Authority
Judged against the Visual Creative Director skill rubric:
canon accuracy, shot usefulness, visual hierarchy, mobile suitability,
coherent sequence (not 3 variations of one illustration).

## Prerequisite resolved before review
The user required explicit `canon_warnings` instead of silent filtering.
`build_visual_scene_package` now returns `canon_warnings: List[str]` that records:
- malformed YAML entries (e.g. `liang.yaml` unquoted `silver_edged_weapon (NOTE...)`
  parsed as a mapping) — coerced AND reported.
- contradictory canon (weapon list mixing a positive weapon with a "no weapon"
  chapter exception).
- filtered non-visual annotations ("carries NO weapon", "unknown hair").
- incomplete locks (no hair/eyes/body/clothing resolved).

This guarantees a clean-looking prompt never hides an incomplete character lock.

## Result: ALL 8 ACCEPTANCE CHECKS PASS
  [PASS] Character identity preserved
  [PASS] Correct clothing/weapon/world
  [PASS] Three visibly different shot roles
  [PASS] No editorial/YAML noise
  [PASS] Prompt usable by current provider
  [PASS] Generic prompt clearly improved
  [PASS] canon_warnings surfaced (prereq)
  [PASS] Coherent 3-shot sequence

VCD rubric per novel (canon accuracy / shot usefulness / visual hierarchy /
mobile suitability / coherent sequence): all OK for HP, EN, SF, HA.

## Concrete prompt examples (post-fix)
- HP Liang: "xianxia cultivation fantasy illustration, vertical 9:16. Scene:
  Liang enters the ruined sect. Subject: dark topknot hair, calm eyes,
  cultivator lean, jade sect robes, red banners nearby, silver edged weapon.
  Setting: Mountain sect courtyard, jade hall, red banners, mist. Shot:
  establishing (wide cinematic). Lighting: golden hour, frost rim. ..."
- EN Kael: opener "cyberpunk mystic fantasy illustration" (HP's "cultivation"
  wording no longer leaks). Setting line no longer contains "n/a (interior)".
- The legacy generic prompt has NO character lock, NO shot role, NO negative
  constraints; VD has all three -> "generic clearly improved" = PASS.

## Known limitations (do NOT block integration; track for Slice 2+)
1. SCENE-MATCHING is exact first-name token only. Real chapter text needs NLP
   scene parsing (later slice). No false Kael/Kai collision (verified).
2. GRAY (SF) canon is INCOMPLETE in the Bible itself: hair/body/weapons =
   "unknown". The Director correctly omits them and emits a canon_warning.
   This is a BIBLE-OWNER task (separate repo), not a Director defect. Slice 2
   (reference-image library) depends on completing Gray's canon.
3. EN weapons show "Soulblade at side, Soulblade, holo UI weapon adjacent" —
   three distinct canon tokens, minor redundancy, not noise. Acceptable for
   Slice 1; tighten in Slice 2.
4. The Director reads Bible YAML directly (separate AIVSB repo). AIVSB composer
   lane remains frozen and untouched. Enrichment via AIVSB is a later slice.

## Next authorized step (after this review passes)
Env-gated integration commit ONLY:
  VISUAL_DIRECTOR_ENABLED=false -> existing make_chapter_image_prompts()
  VISUAL_DIRECTOR_ENABLED=true  -> build_visual_scene_package()
                                    -> package["image_prompts"]
                                    -> existing image generator
                                    -> existing metadata.json contract
Requirements (must hold, will be asserted in the integration commit's guard):
- Legacy path preserved EXACTLY when disabled.
- Return contract stays list[str] (metadata.json image_prompts).
- Fall back to existing prompts if Bible load / char match / package build fails.
- Isolated commit; app.py single-writer handoff respected.

This review artifact is the gate. Integration proceeds only on explicit go.
