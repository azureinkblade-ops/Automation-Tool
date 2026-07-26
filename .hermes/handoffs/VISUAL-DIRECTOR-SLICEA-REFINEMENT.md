# Handoff: Visual Director Slice A — prompt-construction refinement

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-ACCEPTANCE.md (Director accepted as pipeline component)
Commits this slice: see git log (visual_director.py + app.py Director branch + 3 test files).

## Scope (per user's Phase 1-3, restricted to Director refinement)
User accepted the Director (controlled A/B, Legacy 4.6 vs Director 8.7) and split
the next phase into two pipelines:
  Story Bible -> Visual Director -> SDXL+LoRA -> GENERATED IMAGE
                                                      +-> Quality Fixes (Slice B, SEPARATE)
                                                      +-> Evaluation
Slice A = the Director's PROMPT CONSTRUCTION only. Slice B (img2img/inpaint/
upscale/face-fix art-finishing) is a SEPARATE experiment, not touched here.

Slice A changes (all in the Director, env-gated, no provider/metadata change):
1. Per-image NARRATIVE OBJECTIVE. Each shot gets its OWN beat instead of the
   whole scene_text repeated 3x (the A/B "scene repetition" defect). app.py now
   passes the per-image `phrases` as `shots_text` (app.py:30622-30625).
2. Permanent CHARACTER IDENTITY block in every prompt:
   Name / Gender (derived from scene-text pronouns) / Age (canon reborn_adult ->
   young adult) / Build / Appearance (hair, eyes, clothing, weapon). Directly
   attacks the A/B "is this still Liang?" failure.
3. POSE / ACTION per shot (SDXL responds strongly to explicit pose):
   arrival-looks-up / climbs-rests-hand-near-weapon / kneels-before-altar.
4. ENVIRONMENT STATE (location tells WHERE; state tells WHAT HAPPENED): built
   from the matched location's damage_state + weather + fog + ambient_particles
   (e.g. ruined site renders ruined, not pristine). Substring n/a-none filter.
5. Expanded CAMERA taxonomy (wide low-angle / over-the-shoulder / low-angle hero)
   + EMOTION per shot, from the user's brief.
6. WEAPON CANONICALIZATION + DEDUP. The frozen Bible YAML lists
   'silver_edged_weapon' under BOTH clothing and weapons, which produced the
   duplicate 'silver edged weapon, silver edged'. Now collapsed to a single
   'silver-edged sword' (and 'Soulblade' for Kael) WITHOUT editing the frozen
   Bible data. The YAML duplication itself is flagged below for Bible hygiene.

Structure kept PRECISE not verbose (per user): each prompt ~690-820 chars,
well under a wall of text; fields = Narrative Objective / Character Identity /
Action / Setting / Environment State / Camera / Lighting / Power / Emotion.

## Tests (all green)
- tests/test_visual_director.py: 5/5 (character/world/shot/pipeline/novel-isolation)
- tests/test_visual_director_integration.py: 5/5 (OFF byte-identical legacy,
  ON canon-locked, novel isolation, fail-soft x2)
- tests/review_visual_director_slice1.py: 8/8 acceptance checks PASS (was 3 FAIL
  before fixes: shot roles / editorial noise / provider-usable all resolved)
- tests/render_ab/test_harness.py: 10 tests, pytest-based (NOT run here — no
  pytest in codex runtime; validated by the real Run-1 A/B + manual run_ab).
- OFF path verified unchanged (both VISUAL_DIRECTOR_ENABLED and
  AIVSB_REASONING_ENABLED forced off -> identical legacy template, no Director
  markers). NOTE: the codex session shell has AIVSB_REASONING_ENABLED=on, so a
  naive check shows the AIVSB-composed prompt, not legacy — that is an
  environment artifact, not a regression; the integration test forces it off.

## Flagged for separate authorization (NOT silently edited)
- liang.yaml (frozen AIVSB repo) lines 28 + 31: 'silver_edged_weapon
  (NOTE: SDXL dropped to staff, accept)' under clothing AND 'silver_edged
  (fan_chain_horn_bow)' under weapons. Duplicate + malformed. The Director
  canonicalizes at runtime; the YAML should be corrected at source (separate
  repo, needs your explicit go-ahead). Same pattern exists for Kael
  (Soulblade_at_side NOTE, Soulblade (Eclipse Soulblade blueprint)).
- Slice B (art-finishing) and Slice C (automation integration) are deferred per
  the user's phased plan: only after both A and B prove value.

## Next step (re-run the A/B)
Re-run the SAME controlled A/B on the refined Director to confirm the new
structure improves the score AND keeps the per-image narrative progression:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
Same seeds 184732/582941/917364, same engine/LoRA. Compare to Run 1.
Then decide Slice B independently.
