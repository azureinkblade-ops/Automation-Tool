# Handoff: Visual Director Slice 1 (Bible to Visual Scene Package)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commit: (see `git rev-parse --short HEAD` after commit; this lane owns app.py but Slice 1 does NOT touch app.py)

## Intent
Add the missing production layer between the Studio Bible (canon) and image
generation: a function that turns structured Bible knowledge into a
`VisualScenePackage` with character/appearance locks, environment rules, a
3-shot plan, and negative constraints. Validates the premise: can the Bible
produce BETTER image prompts than the current generic string builder?

This is Slice 1 only. No video, no animation, no provider change, no app.py
edit. The existing image generator is untouched; this module only produces
structured prompts.

## Files changed (isolated)
- `visual_director.py` (new) — `build_visual_scene_package(novel, chapter, scene_text)`.
  Reads Bible YAML directly (characters/, locations/, style_guides/) via the
  AIVSB repo path `C:\Users\David\Documents\Inkblade Author Studio\scripts\aivsb`
  (override with AIVSB_BIBLE_DIR). Does NOT depend on the frozen AIVSB composer
  lane (which returns a flat string). AIVSB can enrich later.
- `tests/test_visual_director.py` (new) — 5 acceptance tests, all passing under
  the codex runtime.

## What it must and must not alter
MUST:
- Produce `image_prompts` (list[str]) + `image_sources` (list) compatible with
  downstream metadata.json (Test 4).
- Lock character appearance from Bible (hair, eyes, body, clothing, weapon,
  magic) and keep novel isolation (Kael EN != Kai HA) (Tests 1, 5).
- Enforce world consistency (cultivation setting, resolved environment, magic)
  and 3 purpose-driven shots (Tests 2, 3).
MUST NOT:
- Modify app.py, the image generator, or the AIVSB reasoning lane.
- Migrate or edit the Bible YAML (canon lives in a separate repo).

## Verification
Run under the codex runtime (has `yaml` installed this session):
  python tests/test_visual_director.py
Result: All 5 tests passed (character consistency, world consistency, shot
quality, pipeline compatibility, novel isolation Kael!=Kai).

## Known defects found (Bible data quality, OUT OF SCOPE for this repo)
The Director degrades gracefully, but the source Bible has issues flagged for
the AIVSB/canon owner, not this lane:
1. `characters/liang.yaml` line 28:
   `  - silver_edged_weapon (NOTE: SDXL dropped to staff, accept)`
   is unquoted YAML with parens -> parsed as a nested dict, not a string. The
   Director strips the parenthetical + dedupe so it yields "silver edged
   weapon" in prompts, but the raw Bible entry is malformed.
2. `liang.yaml` `weapons:` includes `carries NO weapon at Ch140` (a chapter-
   specific exception) mixed into the always-true descriptor list. Director
   drops negation tokens, but the canon should separate "default weapon" from
   "chapter exceptions".
3. `body_type`/`age`/`height` are nested under `appearance:` in the YAML, not
   top-level as a naive reader assumes. Director reads both locations.

These are canon-hygiene items for the Bible owner; Slice 1 works correctly
despite them.

## Next step (NOT done; awaiting explicit go)
Wire `build_visual_scene_package()` into `make_chapter_image_prompts()`
(app.py ~30600) as an opt-in path (env flag, e.g. VISUAL_DIRECTOR_ENABLED),
replacing the generic string while keeping metadata.json output identical.
That is a separate isolated commit after this slice is reviewed.

## Downstream-consumer caveat (verified earlier, still open)
`image_quality_gate_for_metadata()` and the TikTok/video path read
`metadata.json` `image_prompts`/`image_sources` only. Slice 1's output maps to
those exact fields, so the video pipeline is unaware of the Director (Test 4).
But no downstream code currently consumes the richer `character_locks`/
`shots`/`negative_prompt` fields; those are for Slice 3+ (reference-image /
img2img consistency).
