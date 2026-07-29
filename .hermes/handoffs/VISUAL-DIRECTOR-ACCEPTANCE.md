---
decision_type: Architecture
status: accepted
date: 2026-07-26
owner: David (user) + Hermes (editing session 20260715_060146_c55923)
subject: Visual Director accepted as a component of the image generation pipeline
---

## Decision
The Visual Director (env-gated integration in app.make_chapter_image_prompts,
commits 5e3e10e + Slice1 d2fae2c/93b9241) is ACCEPTED as a production component
of the image pipeline. It is no longer a design proposal; it has demonstrated,
under controlled conditions, that it improves the part of the workflow that
matters most for posts/videos: guiding SDXL to render an identifiable
protagonist with intentional composition.

## Evidence (Run 1, main-posts LoRA, HP/Liang)
Controlled A/B, single intentional variable = prompt construction.
manifest.json control_check.all_matched = true for all 3 pairs:
  same SDXL checkpoint, refiner (none), LoRA path + weight (0.75), scheduler
  (dpm), steps (resolved 40) / guidance (resolved 7.0), size (768x1344),
  negative prompt, and seed (184732 / 582941 / 917364). effectiveSeed ==
  requestedSeed for all 6 images. No failures.
Therefore any output divergence is attributable to PROMPT CONSTRUCTION, not to
the renderer, LoRA, or generation settings.

## Why the Director won (from the manifest, not assumption)
Legacy prompt: "Scene must clearly depict... Liang enters the ruined sect hall"
-> leans on a proper-noun character SDXL cannot ground -> falls back to
environment. Legacy_1 even rendered pure architecture despite its own
"Avoid generic landscapes" guardrail.
Director prompt: supplies concrete renderable descriptors (dark topknot hair,
calm eyes, cultivator lean, jade sect robes, silver edged weapon) + explicit
Shot/Setting/Lighting -> SDXL produces an actual cultivator.
Mechanism = translate canon into renderable visual language, not merely "add a
character" (both prompts get the same enhance_local_sd_prompt boost).

## User evaluation (authoritative acceptance criterion)
Category            Legacy  Director
Environment          9       8
Character identity   2       9
Composition          5       9
Story clarity        4       9
Shot differentiation 3       9
Canon adherence      3       8
Social-media readability 6    9
Overall              4.6     8.7
Gate harness.evaluate_gate -> recommend_continue = TRUE (4/4 checks PASS).

## Known Director defects (carried into next phase, not blockers)
- Duplicate token "silver edged weapon, silver edged" in every Director prompt.
  Root cause: liang.yaml malformed weapon entry (unquoted parens) coerced to a
  string + canonical weapon. Needs dedup in visual_director.py.
- Canon drift WITHIN the Director sequence: shot 0 robe = deep red (not jade);
  shot 2 = different female warrior with polearm. Liang is not one consistent
  identity across all 3 (gate passed on "recognizable cultivator 3/3", not
  "same Liang 3/3").
- Environment drift: Director_0 read as intact mountain sect entrance, not
  "ruined hall" -> over-constrained pristine architecture vs the ruined brief.

## Agreed next phase: iterative Director refinement (NOT re-litigation)
User's prioritized improvements (2026-07-26):
1. Scene progression per image (not repetition): Image1 Arrival, Image2 Ascent,
   Image3 Formation awakening. Each image gets a PRIMARY narrative objective so
   the 3 frames tell a progressing story (TikTok/Reels/carousel).
2. Dynamic poses / action planning: climbing, reaching, drawing sword, looking
   upward, kneeling before altar. SDXL responds strongly to explicit pose.
3. Environment STATE, not just location: ruined, overgrown, collapsed,
   dust-filled, frost-covered, spiritual energy returning. Prevents drift to
   pristine temples when the story calls for ruins.
4. Power-stage vocabulary (reusable across novel): faint qi threads, dormant
   formation lines, jade mist, sword aura, pressure distortion, spiritual motes.
5. Expanded camera taxonomy beyond establishing/character/action:
   establishing, environment, travel, character, dialogue, combat, artifact,
   reaction, climax; plus cinematic guidance (over-the-shoulder, low-angle hero,
   top-down reveal, extreme close-up, wide environmental reveal).
6. Structure fields to invest in (precise, not verbose): Subject, Setting,
   Action, Camera, Lighting, Mood, Power effects, Narrative objective.
   Do NOT make prompts dramatically longer; structured > verbose.

## Out of scope for this decision
- Post-generation image fixes ("fix things after the images generate"):
  img2img / inpainting / upscale / face-correction. SEPARATE workstream, not the
  Director, not the A/B. Needs its own slice + provider considerations.
- Slice 2 reference-image library / LoRA / IP-Adapter / ControlNet: the user
  redefined the next slice as prompt-construction refinement (cheap, no new
  deps), not the heavier reference-image work originally scoped as Slice 2.
- Realistic-LoRA A/B variant: still outstanding if full both-track proof wanted;
  validation already stands on main-posts.
- AIVSB remains frozen (separate lane).

## Commit boundary for next slice
One concern per commit. Env-gated Director refinement only; no provider change,
no AIVSB change, no Bible edits unless the liang.yaml weapon fix is separately
authorized. Keep generation-evaluation harness as the regression gate.
