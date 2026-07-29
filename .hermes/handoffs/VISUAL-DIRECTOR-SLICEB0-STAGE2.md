# Slice B0 — STAGE 2 THREE-COLUMN MEASUREMENT

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Scope: tightly-scoped Stage 2 (shot 3 / climax ONLY). Single variable = conditioning image.
Question answered: Does detector-derived pose conditioning improve the FINAL image
vs the FROZEN Director, for this shot?

## Setup (everything fixed except the conditioning image)
- Shot: index 2 (climax / "Silver light wakes the dormant formation").
- Seed: 917364 (frozen Director action/climax pairing, Run 8).
- Model: local SDXL base (models/sdxl-base). LoRA: azink_main (main-posts).
- Scheduler/steps/guidance/negative: app defaults (identical across columns).
- Columns:
    legacy          : VISUAL_DIRECTOR off -> generic legacy prompt, NO ControlNet
    director        : VISUAL_DIRECTOR on  -> frozen Director prompt, NO ControlNet
    director_pose   : SAME frozen Director prompt + detector map (ControlNet scale 0.65)
- Conditioning asset: climax_kneel_detected_B.png, STATUS = validation_only
  (see .status.json: known_defects = right_arm_incomplete, merged_hip_keypoints).
  NOT a production asset.

## 7-DIMENSION SCORECARD (vision-inspected, seed 917364) -- REVISED
Two independent fresh re-reads (after a second-opinion review caught an
over-generous first pass) AGREE. The original Stage 2 table below was WRONG
on identity/weapon for director_pose. Engine sidecars confirm director_pose
(seed917364) and iso_prime D (seed917364) used IDENTICAL config
(seed 917364, loraLoaded true scale 0.75, controlnet 0.65, window 0.0-0.75),
so the discrepancy was SCORING, not config. Corrected:

| Metric                | Legacy | Director | Director+Pose | Verdict on D+P |
|-----------------------|--------|----------|---------------|----------------|
| Pose fidelity         | 1      | 1        | 5             | PASS (kneel forced) |
| Interaction fidelity  | 1      | 1        | 1             | FAIL (hand in lap, not on altar) |
| Character identity    | 1      | 4        | 2             | REGRESSION (feminine/androgynous) |
| Weapon fidelity       | 0      | 0        | 0             | FAIL (jian absent; LoRA baseline) |
| Environment fidelity  | 2      | 4        | 4             | retained |
| Composition           | 5      | 5        | 4             | -1 (kneel lowers symmetry) |
| Overall storytelling | 2      | 3        | 3             | modest + (now depicts kneel) |

Key correction: identity 4->2 under the combined config. B' (no LoRA) shows
male 4/5 + jian 4/5, but D' (LoRA ON) loses both -> the LoRA identity/weapon
signal is being overwhelmed by ControlNet at scale 0.65 / window 0.0-0.75.

## CORRECTED BOUNDED CONCLUSION
"Detector-derived OpenPose conditioning successfully controls gross kneeling
posture across multiple seeds (A'/B'/D' all kneel). It does NOT yet support that
the complete Director + LoRA + ControlNet path is ready: in the combined
Director + LoRA + ControlNet configuration, identity fidelity (male -> androgynous)
and weapon fidelity (jian absent) regress, and the altar interaction disappears."

CAUSAL-CLAIM GUARD (per review 2026-07-26):
  DO NOT state "ControlNet is overwhelming the LoRA." That is NOT yet isolated.
  B' uses the manually-written Liang kneeling prompt with LoRA OFF; D' uses the
  frozen Director shot-3 prompt with LoRA ON. B'->D' therefore changes TWO
  variables at once (prompt AND LoRA), so it cannot attribute the regression to
  the LoRA specifically. The supported statement is only:
    "Identity and weapon fidelity regress in the combined Director + LoRA +
     ControlNet configuration."
  The clean LoRA-effect test is config E vs D (same Director prompt + ControlNet,
  LoRA OFF vs ON) -- see NEXT EXPERIMENT (E vs D). Until E exists, the weaker
  phrasing stands.

## GATE VERDICT (corrected)
- A': pose PASS (5/5 both seeds). B': pose+character PASS (4/5 male, 4/5 jian).
- D': pose PASS but OVERALL NON-REGRESSION GATE FAILS (identity + weapon + interaction).
- Therefore: pose conditioning is technically validated; B0 as a complete
  production path is NOT yet validated. Open issue = the combined Director+LoRA+
  ControlNet config regresses identity/weapon; ROOT CAUSE not yet isolated (see
  CAUSAL-CLAIM GUARD -- B' vs D' is confounded by prompt+LoRA).

## SCALE SWEEP -- NARROW INTERPRETATION
The scale sweep answers ONE question:
  "At which ControlNet scale does the frozen Director + LoRA configuration best
   balance kneeling pose against identity, weapon, and interaction fidelity?"
It CANNOT by itself establish WHY identity is weak (that needs E vs D below).

Per-image observation table (vision-scored; sidecars confirm each used the
requested scale + LoRA on + seed 917364):
| Scale | Gross pose (one-knee/stand/seiza) | Male identity | Liang consistency | Jian | Interaction | Anatomy | Env |
|-------|-----------------------------------|---------------|------------------|------|-------------|----------|-----|
| 0.30  | standing (0)                      | 4/5           | (topknot, male)  | 0    | 0           | ok       | hall|
| 0.40  | standing (0)                      | 5/5           | (topknot, male)  | 0    | 0           | ok       | hall|
| 0.50  | standing (0)                      | 5/5           | (topknot, male)  | 0    | 0           | ok       | hall|
| 0.65  | seiza/both-knee (2, NOT one-knee)| 3/5           | androgynous      | 0    | 2           | ok       | hall|

Required observation rule applied: choose a scale only when it clears BOTH
sides of the tradeoff (kneeling retained AND identity not materially regressed
AND quality acceptable). None of 0.30/0.40/0.50/0.65 clears both: below 0.65 the
kneel is lost (standing); at 0.65 the pose appears but identity dips and is
still seiza not one-knee. So the scale axis yields NO acceptable setting.

NOTE: the "0.40 possible balance / 0.50 stronger pose" pattern was only a
HYPOTHESIS; the inspected images show 0.30-0.50 all STAND (kneel lost), 0.65
seiza. Pattern hypothesis REJECTED by inspection.

## D' CONTROLNET-STRENGTH SWEEP (single variable = scale) -- RESULTS
Hold: frozen Director shot-3 prompt + azink_main LoRA (0.75) + detector map B
(validation_only) + seed 917364. Vary ONLY controlnet_scale.

| Scale | Kneel (one-knee) | Male identity | Jian | Hand-altar | Verdict |
|-------|------------------|---------------|------|------------|---------|
| 0.30  | 0 (standing)     | 4/5           | 0    | 0          | kneel lost |
| 0.40  | 0 (standing)     | 5/5           | 0    | 0          | kneel lost |
| 0.50  | 0 (standing)     | 5/5           | 0    | 0          | kneel lost |
| 0.65  | 2 (seiza/both-knee, NOT one-knee) | 3/5 | 0 | 2  | kneel partial, identity dips |

FINDINGS:
1. Below 0.65 the KNEEL DOES NOT SURVIVE at all (subject standing at 0.30/0.40/0.50).
   There is NO "lowest scale that still forces the kneel" in 0.30-0.50. The kneel
   only partially appears at 0.65, and even there it is seiza (both knees), not the
   clean one-knee the detector map specified.
2. Male identity is BEST preserved (4-5/5) exactly when the kneel FAILS (standing).
   At 0.65 where a kneel appears, identity drops to 3/5 and pose is ambiguous seiza.
   => identity and one-knee kneel are in direct tension across the scale axis;
   no scale in {0.30,0.40,0.50,0.65} gives BOTH one-knee + male identity.
3. Jian = 0 at EVERY scale => confirmed LoRA/prompt baseline weakness, independent
   of ControlNet scale. Lowering scale does NOT recover the weapon.

SECOND-OPINION HYPOTHESIS ("lower scale preserves LoRA identity + keeps kneel")
is NOT supported: lowering scale preserves identity but LOSES the kneel entirely.
There is a CLIFF between 0.50 (standing) and 0.65 (seiza-ish), no intermediate that
gives one-knee + male identity.

NEXT SINGLE-VARIABLE TEST 1 -- guidance-window sweep (running now):
  Hold: prompt (frozen Director shot 3) + LoRA (0.75) + map (validation_only)
  + seed 917364 + scale 0.65 (the ONLY scale that forces any kneel).
  Vary ONLY control_guidance_end: {0.40, 0.50, 0.60, 0.75} (per review).
  Hypothesis: ending ControlNet earlier (0.40-0.60) sets body geometry in early
  denoising, then releases ControlNet so the prompt + LoRA restore male identity
  + jian in later steps, WITHOUT losing the kneel.
  Run: tests/render_ab/run_dprime_window_sweep.py (scale fixed 0.65).

WINDOW SWEEP -- RESULTS (single variable = control_guidance_end). Sidecars CONFIRM
each image used the requested cgEnd (0.45/0.55/0.65/0.75), scale 0.65, LoRA on,
seed 917364. NOTE: the file ran ends {0.45,0.55,0.65,0.75} (review's 0.40/0.50/0.60
were approximated by 0.45/0.55/0.65; 0.75 already in set). All four rendered ok.

| cgEnd | One-knee kneel | Male id | Liang cons | Jian | Interact | Anatomy | Env |
|-------|---------------|---------|------------|------|----------|---------|-----|
| 0.45  | 5 (clean)     | 3/5     | 5/5        | 0    | 0        | 5       | 5   |
| 0.55  | 5 (clean)     | 2/5     | 4/5        | 0    | 1        | 4       | 5   |
| 0.65  | 5 (clean)     | 4/5     | 5/5        | 0    | 1        | 4       | 5   |
| 0.75  | 5 (seiza, NOT one-knee) | 5/5 | 4/5   | 0*   | 4        | 4       | 5   |

*end=0.75 "jian 4/5" was the vision model conflating "jian" (character) with
"sword"; it explicitly stated no sword visible -> jian = 0.

FINDINGS:
1. Shortening the window RECOVERED the clean one-knee kneel: cgEnd 0.45/0.55/0.65
   read as a clear ONE-knee kneel (5/5), whereas the longer 0.75 read as seiza
   (both knees). Ending ControlNet earlier improved POSE SPECIFICITY (one-knee vs
   seiza) -- opposite of the vision model's speculative narrative.
2. Male identity varies 2-4/5 across the window (best at 0.65/0.75). No single
   setting gives BOTH clean one-knee AND stable male identity.
3. Jian = 0 at EVERY window setting (as at every scale) -> definitively a LoRA/
   prompt baseline weakness, INDEPENDENT of ControlNet (scale AND window).
4. Window lever improved pose quality but did NOT resolve identity/weapon. The
   remaining question is purely: does enabling the LoRA (under identical ControlNet)
   cause the identity regression? -> answered by E vs D (running).

DECISION LOGIC (per review): pick a setting only if it clears BOTH sides (kneel
retained AND identity not materially regressed AND quality acceptable). No scale/
window combo in this grid clears both. Best pose+identity compromise: cgEnd 0.65
(one-knee 5, male 4) -- but jian still 0.

## E vs D ISOLATION -- RESULTS (clean LoRA-effect test) -- DECISIVE
Same frozen Director shot-3 prompt + detector map B (validation_only) + scale 0.65
+ cgEnd 0.65 + seed 917364. ONLY LoRA differs (E off, D on).

| Config | One-knee kneel | Male id | Liang cons | Jian | Interact | Anatomy | Env |
|--------|---------------|---------|------------|------|----------|---------|-----|
| E (LoRA OFF) | 2 (seated, weak kneel) | 5 (male) | 5 | 0 (dark scabbard, not silver) | 0 | 4 | 5 |
| D (LoRA ON)  | 5 (clean one-knee)    | 1 (female/androgynous) | 3 | 0 | 1 | 4 | 5 |

SIDECRAFT CONFIRM: E ran loraLoaded=False, D loraLoaded=True; all else identical
(scale 0.65, cgEnd 0.65, seed 917364, map B).

ISOLATED CAUSAL FINDING (supported by E vs D; mechanism NOT yet proven):
  With the SAME Director prompt, ControlNet configuration, seed, and pose map,
  enabling azink_main caused the generated character to shift from clearly male
  (E, LoRA off: 5/5) to feminine/androgynous (D, LoRA on: 1/5), while improving
  kneeling compliance (2 -> 5: seated -> clean one-knee).
  That is a CLEAN CAUSAL RESULT for this configuration (single variable = LoRA).
  => It does NOT yet prove WHY the LoRA causes the shift. "The LoRA's training
  aesthetic (androgynous/female cultivator) overrides male + sword" is PLAUSIBLE
  but UNCONFIRMED. Confirming the mechanism would require inspecting the LoRA's
  training dataset, captions, trigger tokens, or validation history (Track 3 work,
  out of scope for this finding).

JIAN FINDING (stated separately, do not conflate with identity):
  The jian was ABSENT with the LoRA BOTH disabled (E) and enabled (D). Therefore
  the weapon failure is NOT caused solely by the LoRA. It belongs to the combined
  prompt / base-model / ControlNet composition problem, potentially compounded by
  the LoRA. Weapon fidelity is its own issue, separate from the identity collapse.

CORRECTED ROOT-CAUSE STATEMENT (mechanism-agnostic, evidence-bound):
  "With identical Director prompt + ControlNet + seed + map, enabling azink_main
   shifts the character from clearly male to feminine/androgynous (5->1) while
   improving kneel compliance (2->5). The jian is absent regardless of LoRA state.
   The identity shift is a LoRA behavior (Track 3 owns root-cause mechanism); the
   weapon failure is a shared composition problem, not LoRA-caused alone."

IMPLICATION FOR B0:
  Pose conditioning (ControlNet) is PROVEN FUNCTIONAL and correctly transfers the
  kneel. The remaining identity/jian failures are LoRA/prompt issues (Track 3),
  NOT the conditioning plumbing. B0's pose path is validated; it should PARK
  pending Track 3 (LoRA retune so male + silver jian survive with LoRA on).
  Finishing (Track 4) is a PRACTICAL PRODUCTION FALLBACK, not a fix for the
  underlying generation config: a controlled inpainting pipeline can potentially
  masculinize/replace the face, add or repair the jian, and fix hands/altar
  contact. It does not resolve the root cause but can ship acceptable frames.

## TRACK 3 -- RESULTS (LoRA scale sweep; single variable = azink_main scale)
Frozen: Director shot-3 prompt + map B (validation_only) + ControlNet 0.65 +
cgEnd 0.65 + seed 917364 + sdxl-base + scheduler/steps/guidance. Scales 0.00 (E)
and 0.75 (D) REUSED (sidecar-confirmed matching config). 0.20/0.35 TIMED OUT
(generator exceeded 360s under ControlNet+low-LoRA; not a config error, just
non-terminating slowness -- rerun with longer timeout if a lower scale is needed).

| LoRA scale | One-knee kneel | Male id | Liang cons | Jian | Interact | Anatomy | Env |
|------------|---------------|---------|------------|------|----------|---------|-----|
| 0.00 (E)   | 2 (seated)    | 5 (male)| 5          | 0    | 0        | 4       | 5   |
| 0.50       | 5 (clean)     | 5 (male, bearded) | 5   | SILVER (hilt) | 3 | 5   | 5   |
| 0.65       | 4 (one-knee)  | 1 (feminine) | 4    | SILVER    | 0        | 4       | 5   |
| 0.75 (D)   | 5 (clean)     | 1 (feminine)| 3    | 0        | 1        | 4       | 5   |

ISOLATED THRESHOLD: male identity collapses between scale 0.50 (male 5/5) and
0.65 (male 1/5). The jian appears at 0.50 AND 0.65 (and 0.75's "0" was the model
conflating character/sword; recheck shows 0.75 also holds a sword per D render).
=> SCALE 0.50 is the SWEET SPOT: clean one-knee kneel + male identity + silver jian
all present simultaneously. This is decision-logic OUTCOME 1 (intermediate works).

DECISION: promote LoRA scale 0.50 as the candidate B0 configuration. Rerun across
2-3 seeds (establishing 184732, character 582941, action 917364) to confirm the
male-id + jian + kneel combination is seed-stable before promotion. The 0.20/0.35
timeout gap remains: if a lower scale is desired for style, rerun with a longer
generator timeout; but 0.50 already satisfies the target, so lower is optional.

NOTE on jian: the jian is NO LONGER absent at the right LoRA scale (0.50/0.65) --
the earlier "jian 0 at every scale" in the scale/window sweeps was because those
used 0.75 (D), where the model conflated jian-character vs jian-sword. At 0.50 the
silver jian is clearly present. So weapon fidelity is NOT a separate hopeless issue
at scale 0.50; it co-appears with male identity. The jian gap was scale-dependent,
not a standalone composition defect.

## E vs D ISOLATION -- SPEC (the experiment that produced the above)
  This is the only experiment that can isolate whether the LoRA is the cause of
  the identity/weapon regression. B' vs D' is confounded (prompt AND LoRA both
  change), so it cannot. Run TWO configs with the SAME frozen Director prompt,
  same seed, same map, same scale (0.65), same guidance window, same scheduler,
  everything identical except LoRA:
    E: Director prompt + ControlNet, LoRA OFF
    D: Director prompt + ControlNet, LoRA ON
  Compare E vs D on: male identity, Liang consistency, jian, interaction, anatomy.
  ONLY after E vs D can we state "the LoRA is overwhelmed by ControlNet" vs
  "the combined config regresses regardless of LoRA." Until then, the supported
  phrasing is strictly:
    "Identity and weapon fidelity regress in the combined Director + LoRA +
     ControlNet configuration."
  Driver: tests/render_ab/run_dprime_e_vs_d.py (to be written after window sweep).

If window sweep + E/D both fail to preserve both pose and identity, the blocker
moves to Track 3 (LoRA/identity tuning) and B0's pose path parks; the conditioning
plumbing itself is proven functional.

## Evidence boundary preserved
- Manifest records pose_condition_source=detector_output, the validation_only
  status, known_defects, controlnet_model/scale, source+map sha256.
- Scale-sweep sidecars CONFIRM each image used the requested controlnetScale
  (0.30/0.40/0.50/0.65), loraLoaded true, seed 917364. Scale was NOT inferred
  from directory names alone (per review requirement).
- The earlier (retracted) "known ControlNet+LoRA conflict" claim is NOT supported.
  The supported statement is only: identity/weapon regress in the combined
  Director+LoRA+ControlNet config; root cause NOT yet isolated (needs E vs D).

## TRACK SPLIT (per user architecture)
- Track 1 (Complete): Prompt architecture. Legacy(identity1,weapon0) ->
  Director(identity4,env4) shows the Director's gains are real and retained.
- Track 2 (Validated for POSE only): Pose conditioning forces a kneel under the
  Director+LoRA+ControlNet config (kneel appears at scale 0.65). But the combined
  config FAILS the non-regression gate on identity/weapon. Pose plumbing is
  proven; PROMOTE only after a config clears both pose + identity (window sweep
  and/or E vs D).
- Track 3 (NOT RESOLVED -- CORRECTED 2026-07-26): The earlier "seed-stable"
  claim used per-position seeds 184732/582941/917364 mapped to DIFFERENT
  shot prompts (establishing/climb/climax) -- that proved PROMPT-generalization,
  not seed-stability of one prompt. A CORRECTED run (fresh backend per seed,
  seeds=(seed,), index=0, because LocalSDAppBackend.render() HARDCODES
  self.seeds[index] at harness.py:176 and ignores any passed seed) rendered the
  SAME climax prompt at scale 0.50 with TWO different maps:
    * With MAP B (validation_only): kneel 4-5/5, male 5/5, jian YES -- RELIABLE.
    * With MAP C (authored, limb-complete): seeds 917364=standing/female/no-jian,
      241981=kneel/male/jian (TARGET), 581203=standing/male/no-jian,
      772944=two-figures/androgynous/standing. => 1-of-4 seeds hit target.
  KEY FINDING: Map C is limb-complete and passes the visual preprocessing gate,
  but it FAILS to drive the kneel in the generator (seed-unstable, mostly
  standing). Map B is visually defective but RELIABLY drives the kneel.
  => NEITHER map currently satisfies the full activation gate.
  Root cause hypothesis (UNCONFIRMED): Map B's native-detection skeleton
  carries subtler pose cues (torso lean, limb angles) the generator responds
  to; Map C's idealized skeleton is interpreted more weakly / overridden.
  This is a POSE-MAP fidelity problem, not a LoRA-scale problem.
- Track 4 (Open, fallback): Finishing pipeline (Slice B: inpaint/upscale/facefix)
  is a PRACTICAL production fallback (can masculinize face, add/repair jian, fix
  hands/altar) -- not required for the climax shot at scale 0.50, but available as
  safety net. Not a root-cause fix.
- Track 5 (Open): Automation integration (Slice C).

## Next steps (not executed)
1. OPEN: the pose map is unresolved, but the PREMISE changed.
   Map B was labelled "validation_only / defective / right-arm-incomplete /
   merged-hips" from a VISUAL review that was WRONG. Authoritative
   diagnosis from the installed controlnet_aux source (draw_bodypose limbSeq,
   util.py:86-92) + an index-labelled diagnostic of the raw 18-pt body
   array shows: arms COMPLETE (shoulder->elbow->wrist present both sides);
   hands None = no hand detected (NORMAL, not a defect); the "merged hips"
   were a misread -- index 9 (l_hip) is misplaced at floor level (y=0.855)
   and edges [2,9]+[9,10] draw a VERTICAL line shoulder->floor that IS
   the kneeling-leg visual. So Map B's only oddity ACTIVELY PRODUCES
   the kneel. Repairing it (moving idx9 to mid-torso) would REMOVE the
   kneel line and likely REGRESS pose compliance.
   => The user-directed B2a (hip-only) / B2b (hip+arm) repairs are now
      framed as CAUSAL PROBES (do they preserve or destroy the kneel?),
      not assumed improvements. Run Map B baseline (corrected 4-distinct-seed
      harness) FIRST to confirm Map B is truly robust; then B2a/B2b as probes.
2. Promotion is SHOT-SCOPED (climax kneel only). Extend to EN/SF/HA after HP if
   needed, per original plan.
3. Commit B0 + Track 3 work only on explicit user approval (publish-deferred).

## MAP B BASELINE (CORRECTED harness, 4 DISTINCT seeds, 2026-07-26)
Same frozen Director climax prompt + LoRA 0.50 + ControlNet 0.65 + cgEnd 0.65,
fresh backend per seed (seeds=(seed,), index=0). This is the linchpin
comparison the user required -- and it REVERSES the earlier "Map B defective"
premise with direct same-prompt evidence:

| Seed | One-knee kneel | Male | Jian | Verdict |
|------|---------------|-------|------|---------|
| 917364 | 4/5 (kneeling) | 5/5 | NO | kneeling male |
| 241981 | 4/5 (kneeling) | 3/5 (androg) | NO | kneeling, male-lean |
| 581203 | 4/5 (kneeling) | 4/5 | YES | kneeling male + jian |
| 772944 | 4/5 (kneeling) | 3/5 (androg) | NO (pouch) | kneeling, male-lean |

|=> Map B delivers a clear KNEEL on ALL 4 seeds (4/5 each) and MALE on
|all 4 (3-5/5). The jian is seed-variable (1/4 visible) -- but the
|kneel+male combo (the B0 point) is 4/4 ROBUST. Contrast Map C
|(limb-complete, authored): only 1-of-4 kneeled. So the user's
|hypothesis is CONFIRMED by direct same-prompt evidence: Map B reliably
|drives the kneel; Map C (clean) does NOT.
|
|PROVEN (measured):
|- Pose-conditioning infrastructure works (ControlNet functioning, Director
|  prompt not the blocker, LoRA coexists with ControlNet).
|- Map B consistently produces the desired kneeling pose (4/4 distinct seeds
|  at LoRA 0.50). Map C does not (1/4) under equivalent conditions.
|- Earlier "broken arm / merged hips" diagnosis was INCORRECT (arms
|  complete; hands just undetected = normal; hips not merged).
|- Kneeling behavior is NOT explained by a single obvious edge or single
|  keypoint position alone (see E1/E2 below).
|
|STILL UNKNOWN:
|- Whether a minimally *repaired* Map B could preserve kneeling while
|  improving anatomical correctness. (NOT established either way.)
|- Whether such a repaired map would improve downstream generation quality.
|- Which *subset* of lower-body geometry actually drives the ControlNet
|  response. E1/E2 ruled out single-factor, did not locate the
|  multi-factor cause.
|
|E1 / E2 (static-map causal probes, CPU-only, NO generator):
|- E1: removed only edge [2,9] from Map B's recovered raw array,
|  re-rendered the skeleton. Static map retained a recognizable
|  KNEELING SILHOUETTE.
|- E2: moved ONLY idx9 up by 6% of image height; every other
|  joint untouched. Static map retained a recognizable KNEELING
|  SILHOUETTE.
|- What E1/E2 establish: the rendered pose map still LOOKS like a
|  kneel after these minimal edits. They did NOT establish
|  equivalent ControlNet behavior, and did NOT rule out those
|  factors at generation time. (Map C was limb-complete and "looked
|  like a kneel" yet drove standing 3/4 -- so static appearance is
|  not a substitute for a generator test.)
|- Static inspection is a PRE-FILTER only. Acceptance requires the frozen
|  same-prompt, four-distinct-seed GENERATOR test.
|
|RETIRE original B2a/B2b plan: those were LARGE edits based on the
|INCORRECT "broken arm / merged hips" defect model, so they are withdrawn.
|This does NOT state that repairs are unnecessary -- only that the specific
|B2a/B2b edits are no longer justified by the (now-falsified) defect.
|
|PROPOSED next experiment (R1/R2/R3), NOT authorized work:
|- R1: minimal anatomically-motivated repair (one or two joints only),
|  e.g. correct idx9 from its invalid floor position to a plausible hip
|  location while KEEPING the low knees/ankles that encode the
|  kneel. Then validate with an ACTUAL generator run (not just a
|  static render).
|- R2: another minimal repair only if R1 succeeds (preserves kneel +
|  improves correctness).
|- R3: stop immediately if pose compliance regresses.
|Every modification stays incremental and GENERATOR-VALIDATED; the static
|render is a cheap pre-filter, never the acceptance test.
|
|MILESTONE (well-supported):
|Slice B0 infrastructure is validated. Map B is the current
|best-performing conditioning asset for this shot. Remaining work is
|conditioning-asset optimization, not pipeline debugging.
|
|## PHASE 1 — FROZEN BASELINE (2026-07-26)
|Map B is the BASELINE, not the final solution. Every future experiment
|changes ONLY the intentionally-tested variable. Frozen config (the
|stable benchmark for all R* runs):
|- Director prompt: FROZEN shot-3 climax prompt (single-person Liang,
|  kneeling before altar). NOT edited.
|- LoRA: azink_main, scale 0.50, enabled. NOT changed until pose-map
|  question is closed.
|- ControlNet: xinsir/controlnet-openpose-sdxl-1.0, scale 0.65,
|  guidance_start 0.0, guidance_end 0.65. NOT changed.
|- Seeds (test set, 4 distinct): 917364, 241981, 581203, 772944.
|- Model versions: SDXL base (app local-sd backend) + ControlNet path
|  fixed. NOT changed.
|- Pose map: the ONLY variable per experiment (Map B baseline -> R1 -> ...).
|Acceptance gate = frozen same-prompt, 4-distinct-seed GENERATOR test
|(run_map_compare.py). Static render is pre-filter only.
|
|## PHASE 2 outcome — R1 REJECTED (2026-07-26)
|Status: REJECTED — POSE_AND_IDENTITY_REGRESSION. Map B stays the
|frozen baseline. R1 NOT promoted. R2 NOT run (conditional on R1
|success). Registry unchanged and still points to Map C
|(`climax_kneel_detected_C.png`); Map B is the frozen EVIDENCE baseline,
|not yet wired. Flag OFF, so no active runtime effect. Nothing committed.
|Generator validation (identical frozen 4-seed harness, --map R1):
|- 917364: kneel 5/5 PRESERVED, male 1/5 (female) -> identity regressed.
|- 241981: kneel 0/5 (STANDING), male 0/5 (female) -> both regressed.
|- (581203, 772944: not scored for the gate decision; even perfect
|  results would leave R1 at <=2/4 acceptable vs Map B 4/4 kneeling.
|  Cannot reverse rejection.)
|GATE RESULT: fails BOTH required conditions (preserve pose compliance,
|preserve identity). Reject R1 immediately, keep Map B, no more work
|on this branch.
|WHAT R1 ESTABLISHED (do not overstate): moving only idx9 from its
|floor-level position to a plausible hip location does NOT preserve
|the working Map B behavior. The response is SEED-DEPENDENT (one seed
|kept kneel but lost identity; another lost both). This does NOT prove
|idx9 alone drives kneeling -- it demonstrates this particular
|single-joint repair changes the conditioning image enough to cause
|unacceptable downstream regressions.
|NEXT LANES (separated, no execution now):
|- Pose optimization: design a DIFFERENT minimal repair informed by
|  R1, only under a newly authorized experiment. R1 branch closed.
|- Weapon fidelity: keep Map B unchanged; address jian independently
|  via prompt or finishing work (Phase 4, separate track).
|
|## PHASE 3 — only if R1 succeeds
|One additional minimal correction (one joint / one limb / one tiny fix).
|Never combine multiple fixes. Same frozen harness.
|
|## PHASE 4 — Weapon fidelity (SEPARATE track, after pose map settled)
|Address sword visibility / grip / sheath / orientation. NOT a pose-map
|problem. Separate variables: prompt wording, LoRA balance, regional
|prompting, inpainting if needed. Do NOT mix into pose experiments.
|
|## PHASE 5 — Generalization (only after climax solved)
|standing / walking / combat / meditation with the EXACT same pipeline.
|Validates architecture, not a lucky single pose.
|
|## EXCLUDED (unnecessary variables)
|chasing another reference image; switching detectors; rewriting the pose
|library; tuning multiple parameters simultaneously; changing LoRA again
|before the pose-map question is closed.
|
|## STRATEGIC PIVOT — freeze Map B, open Track 4 (weapon fidelity) (2026-07-26)
|Decision: STOP pose-map optimization as the active lane; shift effort to
|weapon (jian) fidelity. Rationale (user-directed):
|- Map B = 4/4 kneeling + acceptable identity + stable across seeds. That
|  was the originally hardest target and it is MET.
|- Map C failed (1/4 kneel); R1 regressed (pose+identity). So we have
|  shown: pipeline works, baseline works, and at least one plausible
|  minimal repair makes things WORSE. Expected return on the NEXT pose
|  repair is now LOWER -- no clear defect remains to fix; the search
|  space is now broader/less guided.
|- Remaining weakness = inconsistent jian visibility (seed-variable, ~1/4
|  at LoRA 0.50). That is a NARROWER problem with HIGHER practical
|  payoff: a kneeling Liang with a missing sword is still the correct
|  scene; a standing Liang with a perfect sword is the WRONG scene. The
|  pose communicates the story beat; the sword refines it.
|ACTIONS:
|- FREEZE Map B permanently as the current PRODUCTION BASELINE for this
|  shot. No further pose-map edits without a newly authorized experiment.
|- CLOSE the R1 branch as REJECTED (POSE_AND_IDENTITY_REGRESSION). Done.
|- OPEN a new Track 4 focused ENTIRELY on weapon fidelity (jian
|  visibility / grip / sheath / orientation), keeping Map B unchanged.
|- POSE OPTIMIZATION goes DORMANT. Burden of proof SHIFTS: any future
|  pose experiment must start from a SPECIFIC hypothesis
|  ("this particular structural change should improve X because..."),
|  not "let's try another repair." Do NOT run an open-ended joint-edit
|  search. Return to pose optimization ONLY if:
|  (a) a specific anatomical error with a concrete rationale emerges,
|  (b) a better native-skeleton detector is discovered, or
|  (c) the pipeline must generalize to many different kneeling poses.
|EFFORT GUIDANCE (if 10h available): ~7-8h weapon fidelity + finishing;
|~2-3h reserved for future pose work ONLY under a new hypothesis.
|  Map B is the frozen production baseline for the climax kneel shot;
|  the open item is weapon fidelity (Track 4), not the pose map.
|
|## TRACK 4 — WEAPON (JIAN) FIDELITY (authorized 2026-07-26)
|Pose map FROZEN (Map B). Baseline visible-jian rate: 1/4 (seed 581203).
|
|T1 — PROMPT-PHRASE VARIANT: REJECTED (ineffective).
|Changed ONLY `_WEAPON_LOCK` from "sheathed" to "drawn and held ... blade
|fully visible" across the 4 frozen seeds. Jian visible: 0/4; kneel
|preserved all 4. Supported conclusion: this specific explicit-visible
|phrase did NOT improve jian visibility; the "sheathed wording alone
|causes omission" hypothesis is falsified. This does NOT prove all prompt
|wording is irrelevant or assign the unresolved cause to seed/LoRA.
|
|T2 — LoRA-OFF ISOLATION: REJECTED.
|Frozen Map B, original frozen prompt, ControlNet 0.65/end 0.65, four
|distinct seeds; ONLY azink_main changed from loaded@0.50 to disabled.
|Sidecars: seed matched all 4; loraLoaded=False all 4. Jian visible: 0/4.
|Identity weakened/androgynous on multiple seeds; kneel also weaker on
|seed 581203. Gate (jian >=3/4 + preserve pose/identity) FAIL.
|Supported conclusion: this specific LoRA-off variant does NOT restore
|the jian and is not an acceptable production balance. It does NOT prove
|LoRA can never affect weapon fidelity.
|
|T3 — LOCALIZED INPAINTING FALLBACK (evidence-only, seed 917364):
|- Approved narrow mask: outer hip/robe only; avoids face, torso center,
|  both hands, and front knee.
|- T3a text-only inpaint @ strength 0.95: NULL (no jian); outside-mask
|  pixels exactly unchanged.
|- T3b structural-guide inpaint @ strength 0.55: FAIL practical gate
|  (ribbon-like strip, insufficient weapon recognizability).
|- T3c refined structural guide + negative ribbon/sash controls @ strength
|  0.25: PASS PRACTICAL FALLBACK. One recognizable sheathed Chinese jian
|  with wrapped hilt, horizontal guard, rigid dark scabbard, and end cap;
|  male identity + kneeling pose preserved. Independent re-read agrees the
|  weapon is unmistakable; attachment is somewhat stiff/pasted-on, so this
|  is NOT a polished-final-art pass.
|- Provenance: output
|  `tests/render_ab/output/track4_inpaint/seed917364_jian_inpaint_guided_v2.png`;
|  SHA-256 `29bcb57dac55706680c8fb1e607e69288c7edf0378c39ae31400af41ab2bd968`.
|  Outside-mask absdiff mean=0.0, max=0 (exact preservation).
|BOUNDARY: localized finishing fallback is VALIDATED on ONE selected Map-B
|asset. Automated reliability across seeds/assets is NOT MEASURED. No
|production integration, Map-B edit, registry edit, flag flip, or commit.
|
|B2a/B2b GPU runs: not executed (retired). R1: REJECTED (closed).
|- Track 5 (integration): deferred.
|- Nothing committed (publish-deferred).
|- Scaffold remains env-gated OFF (VISUAL_DIRECTOR_POSE_CONDITIONING=0).
|  Map B remains the frozen EVIDENCE baseline; registry remains Map C.
|
|## STAGE 2 OBJECT REFINEMENT BUILD SLICE (2026-07-26)
|Status: IMPLEMENTED AND LOCALLY EXERCISED; NOT APP-INTEGRATED OR PRODUCTION-READY.
|Architectural role: intentional Stage 2 localized object refinement, not a
|fallback and not part of the frozen Visual Director prompt layer.
|
|Implemented files:
|- `object_refinement.py`: CPU-only contract/orchestrator. Feature flag
|  `VISUAL_OBJECT_REFINEMENT_ENABLED` defaults OFF. Disabled returns source and
|  never calls backend. Enabled flow validates non-empty same-size mask, invokes
|  an injected backend, creates diff + provenance, independently verifies zero
|  outside-mask changes, quarantines unreviewed candidates as `pending_review`,
|  returns source on rejection, and promotes only an accepted candidate.
|- `finalize_review(...)`: re-hashes source + candidate and writes a separate
|  `final-provenance.json`; pending provenance remains immutable.
|- `local_object_refinement_backend.py`: subprocess adapter with sidecar-echoed
|  model/seed/parameter provenance.
|- `local_object_refiner.py`: local SDXL inpaint CLI; optional structural guide
|  + LoRA; exact outside-mask compositing; no external/paid provider path.
|- `tests/test_object_refinement.py`: 8 contract/backend tests including empty
|  mask and outside-mask adversarial gates.
|- `tests/render_ab/run_stage2_refinement_replay.py`: evidence-only real replay.
|
|REAL REPLAY (new service + new backend CLI):
|- Source: frozen Map-B seed 917364 render; existing approved hip mask + guide.
|- Service first returned `pending_review`; effective output remained source.
|- Candidate manually reviewed: ACCEPT (one coherent sheathed jian; male identity,
|  kneeling pose, hands/anatomy preserved; diff localized).
|- Finalizer re-hashed artifacts and promoted candidate in a separate final record.
|- Candidate: `tests/render_ab/output/stage2_refinement_replay/candidate.png`;
|  SHA-256 `0eff5024bbac2563c058e942568e9f658e10ed53bcf33fb0ab961ca9068a89a1`.
|- Final record: `tests/render_ab/output/stage2_refinement_replay/final-provenance.json`.
|- Outside-mask changed pixels=0; max channel delta=0.
|
|VERIFICATION:
|- Refinement + render harness pytest: 18 passed.
|- New refinement module alone: 8 passed.
|- Visual Director unit: 5 passed; integration: 5 passed.
|- Creative review script: all acceptance checks passed.
|- Pose scaffold: 7 passed, 1 FAILED because test expects Map B while live
|  `pose_resolver.py` still points to Map C. Known unresolved registry mismatch;
|  not caused or changed by this slice. Therefore NOT full regression green.
|- New Python files compile; local refiner CLI help exercised.
|
|BOUNDARIES:
|- `app.py` untouched (another lane owns it).
|- No publishing integration, registry edit, pose flag flip, automatic review,
|  commit, or production activation.
|- Reliability across other seeds, objects, masks, and compositions NOT MEASURED.
|
|## STAGE 2 VALIDATION MILESTONE V0 (2026-07-26)
|Status: HARNESS_VALIDATED; RELIABILITY_NOT_MEASURED.
|
|Contract:
|- `.hermes/evidence/stage2-refinement-validation-contract.md`
|- V0 reuses one accepted replay to validate mechanics only.
|- V1 requires 20-50 independently reviewed cases; no broad GPU run before
|  allocation + utility thresholds are approved.
|- V2 changes one sensitivity variable at a time only after V1.
|- Runtime activation, app.py integration, registry edits, automatic review,
|  publishing, and post-hoc threshold selection remain prohibited.
|
|Implemented validation tooling (schema v3):
|- `stage2_validation.py`: CPU-only fixture preflight, hash-bound evidence
|  collection, manifest/backend frozen-config reconciliation, structured-review
|  aggregation, explicit denominators, NOT_MEASURED serialization, decision
|  taxonomy, two-sided 95% Wilson intervals, stratified failure clustering,
|  and deterministic JSON report CLI.
|- `tests/test_stage2_validation.py`: 17 tests covering valid preflight,
|  incomplete provenance, denominator discipline, source-hash tamper, explicit
|  NOT_MEASURED, duplicate IDs, empty masks, sample floor, and seed drift.
|
|V0 artifacts:
|- Manifest: `.hermes/evidence/stage2-validation-pilot-manifest.json`
|- Structured review: `.hermes/evidence/stage2-validation-pilot-review.json`
|- Report: `.hermes/evidence/stage2-validation-pilot-report.json`
|- Decision: HARNESS_VALIDATED, total cases=1.
|- Acceptance and all seven visual gates: 1/1 for the reused accepted case.
|- Exact outside-mask preservation: 1/1.
|- Preparation time, review time, intervention cycles: NOT_MEASURED.
|- This does NOT measure cross-scene, cross-object, cross-mask, or cross-seed
|  reliability. Overall decision remains RELIABILITY_NOT_MEASURED.
|
|V1 execution package:
|- `.hermes/evidence/stage2-validation-v1-allocation-proposal.json`
|- 24 unique unassigned slots: sheathed sword 6; drawn sword 4; weapon/scabbard
|  repair 4; non-weapon prop 4; hand repair 3; clothing defect 3.
|- Facial cleanup excluded pending a separate stricter policy.
|- V1 is descriptive: measure actual acceptance, failure clusters, second-pass
|  frequency, and manual effort; no speculative utility pass/fail threshold.
|- Safety invariants remain predeclared at 100%.
|- Utility thresholds may be selected after V1, then must be frozen and tested
|  against a new independent V1H holdout. V1 cannot validate thresholds selected
|  from V1.
|- Every binomial rate reports numerator, denominator, point estimate, and a
|  two-sided 95% Wilson interval overall and by declared stratum.
|- Because V1 is quota-stratified rather than a random population sample,
|  population generalization remains NOT_ESTABLISHED.
|- Production preflight blocks duplicate source-image hashes; case independence
|  remains an APPROXIMATE assumption even with distinct sources.
|- Fixture status: FROZEN_AND_PREFLIGHTED. The 24 cases use 24 distinct source
|  hashes and preserve the 6/4/4/4/3/3 object-class allocation. Source mix is
|  EN 18, HA 3, HP 3, SF 0; cross-IP and SF generalization remain NOT_ESTABLISHED.
|- Failure-inclusive schema v3 reports backend success, no-op, second-refinement
|  frequency, and generation duration. Backend-failed attempts remain in the
|  full-attempt and acceptance denominators without requiring candidate
|  provenance or human review.
|- `tests/render_ab/run_stage2_v1.py` requires `--execute` plus a manifest-hash-
|  bound explicit approval record; dry-run cannot invoke the backend.
|- Status: EXECUTION COMPLETE — AWAITING INDEPENDENT VALIDATION REVIEW. (The
  `AWAITING_EXPLICIT_GPU_APPROVAL` label is historical; the 24-case run was
  authorized and completed 2026-07-26. See the EXECUTED block below.)
|
|## STAGE 2 V1 DESCRIPTIVE STUDY (EXECUTED 2026-07-26)
|Status: COMPLETED; RELIABILITY_DESCRIBED_THRESHOLDS_NOT_FROZEN.
|
|Authorization: explicit manifest-hash-bound approval record
|`.hermes/evidence/stage2-v1-gpu-approval.json` (scope
|`stage2-v1-gpu-execution`, manifest SHA-256
|`4d610e2a5100dc099ba63a110859cbd2c2ee54a50b177d9ce7a94808713dae93`)
|authorized GPU execution of the frozen 24-case manifest, quarantine as
|pending_review, no publish/integration/flag change, continue-on-failure,
|terminal record per attempt.
|
|Execution (schema-v3 runner, public service/backend boundary):
|- 24/24 cases attempted; 24/24 completed; 0 backend failures.
|- 24/24 candidates quarantined as `pending_review`; 0 accepted by the service
|  (acceptance is a separate human-finalization step); 0 automatic-publish events.
|- 24/24 exact outside-mask preservation (changed pixels=0, max delta=0).
|- Mean generation 16.4s/case; no second-refinement attempts; 0 manual cycles.
|- One smoke case (v1-001) generated first against a one-case subset manifest
|  with its own hash-bound approval, then reused via `--resume` for the full run.
|
|Structured human review (Hermes vision pass, frozen 7-gate set):
|- 24/24 ACCEPT on object_recognizable, placement_attachment_valid,
|  no_duplicate_floating_substitution, identity_preserved, pose_preserved,
|  anatomy_preserved, clothing_composition_preserved.
|- All changes localized to the masked target region per source/candidate/diff
|  contact-sheet review.
|
|Schema-v3 V1 report (`.hermes/evidence/stage2-validation-v1-report.json`):
|- decision_status: RELIABILITY_DESCRIBED_THRESHOLDS_NOT_FROZEN (descriptive,
|  NOT a production-activation pass/fail gate).
|- acceptance_rate: 24/24 (1.0; Wilson 95% 0.862-1.000).
|- exact_outside_mask_preservation_rate: 24/24 (1.0; 0.862-1.000).
|- backend_success_rate: 24/24 (1.0; 0.862-1.000).
|- no_op_rate: 0/24 (0.0; 0.000-0.138).
|- second_refinement_frequency: 0/24 (0.0; 0.000-0.138).
|- Per-object-class acceptance (all 100% within small strata):
|  sheathed_sword 6/6, drawn_sword 4/4, scabbard_weapon_repair 4/4,
|  non_weapon_prop 4/4, hand_repair 3/3, clothing_defect 3/3.
|
|Scope limitations (unchanged from preflight):
|- Source mix EN 18 / HA 3 / HP 3 / SF 0. Cross-IP generalization NOT_ESTABLISHED.
|- Quota-stratified, not a random population sample; case independence APPROXIMATE.
|- 24 observed successes cannot distinguish a genuinely robust pipeline from
|  lucky sampling; narrow Wilson lower bounds reflect the small n.
|- V1 measured reliability; it did NOT validate any utility threshold. Thresholds
|  (if adopted) must be frozen after V1 and tested on a new independent V1H holdout.
|
|What this does NOT establish:
- Production readiness or activation permission (still prohibited).
- Cross-IP / SF generalization.
- That every future object/seed/mask will succeed (no backend failures observed,
  but the sample cannot prove robustness).

## CRYPTOGRAPHIC EVIDENCE MANIFEST (added 2026-07-26)
The V1 artifact set is anchored by a SHA-256 evidence manifest so the report
can be shown to derive from an exact, verifiable artifact set:
- `.hermes/evidence/stage2-v1-evidence-manifest.json` — 99 artifacts
  (manifest + approval + report + 24 execution records + 24 reviews +
  24 provenance + 24 candidates), each with SHA-256 + byte size, bound to
  manifest SHA-256 `4d610e2a...`.
- `tests/render_ab/verify_stage2_v1_evidence.py` recomputes every digest and
  exits non-zero on any mismatch. Verified `VERIFY_OK` over 99 artifacts.

### Reproducible-execution bundle (extended chain-of-custody, 2026-07-26)
`.hermes/evidence/stage2-v1-exec-bundle.json` records the execution context so
the run is auditable, not just the artifact bytes:
- git HEAD `4e10045` + dirty-tree diff hash `364ce5b9...` (covers the four
  production-path files carrying the uncommitted Slice B0 ControlNet diff).
- Code identities (SHA-256) for generator/collector (`stage2_validation.py`),
  runner, review-writer, verifier, introspector, evidence-builder, review-sheet
  builder.
- Exact command lines for generate / report / review / verify.
- Interpreter `.venv-gpu/Scripts/python.exe`, Python 3.12.13; packages
  torch 2.13.0+cpu, diffusers 0.39.0, pillow 12.2.0, numpy 2.4.3,
  transformers 5.14.1, controlnet-aux 0.0.10, huggingface-hub 1.24.0.
- Model/LoRA file hashes: sdxl-base `31e35c80...`, lora_azink_main `5093d905...`.
- Run window 2026-07-26T19:46:47 -> 19:53:51 (from execution-record timestamps).
- Parent hash over the canonicalized bundle: `63e59f6f...`.

CAVEAT (recorded honestly, not resolved): the introspected torch build string
is `2.13.0+cpu`, yet 24 candidates were generated on GPU. torch failed to *import*
in the introspection context (OSError on the DLL), so the `+cpu` string is the
recorded package *metadata*, not proof of no-CUDA at run time. The GPU name was
not capturable here; the execution records remain the authoritative generation
config. The bundle flags this rather than asserting a CUDA build.

LIMITATION: the bundle records environment and code identities; it does NOT
cryptographically prove the report code was the code that produced the report,
nor that the reviews were produced by the claimed visual process. It enables a
reviewer to check those identities against the running system. The verifier's
`--exec-bundle` flag re-hashes the code files and reports (non-fatally) any
drift since the bundle was generated.

Provenance chain (internally linked via the same manifest hash):
manifest(`4d610e2a...`) -> approval(`manifest_sha256=4d610e2a...`) ->
24 execution records (each `manifest_sha256=4d610e2a...`, `automatic_publish_events=0`)
-> 24 provenance (`status=pending_review`, `outside_mask_changed_pixels=0`,
`outside_mask_max_channel_delta=0`) -> 24 reviews (`overall_accept=true`, 7 gates)
-> schema-v3 report (`decision_status=RELIABILITY_DESCRIBED_THRESHOLDS_NOT_FROZEN`).

The report regenerates from the stored artifacts (`stage2_validation.py --manifest ...`),
so it is derived from files rather than existing only as prose.

## STEP 1 (2026-07-27): HIGH-RESOLUTION SUBTLE-DEFECT REVIEW (no GPU)
Agreed process (user): Freeze V1 artifacts -> HR subtle-defect review ->
freeze V1 report -> freeze V1-derived thresholds -> design V1H -> execute V1H.
"24/24" is a descriptive gate result, NOT an activation decision.

Deliverables produced (all free; candidates already on disk, unmodified):
- `tests/render_ab/defect_review_rubric.md` — ordinal 0-3 scale (0=severe,
  3=none) over 10 items: grip_alignment, blade_perspective, finger_intersections,
  lighting_consistency, metal_reflections, edge_blending, texture_continuity,
  halo_artifacts, scabbard_attachment, overall_realism. Blocking = grip/finger/
  edge/halo scoring 0.
- `tests/render_ab/record_stage2_v1_defect_review.py` — writes per-case
  `defect-review.json` with scores + blocking-defect detection.
- `tests/render_ab/build_stage2_v1_hr_sheets.py` — 24 full-res `candidate|diff`
  sheets with case ID in a SEPARATE header strip (no in-image label, addressing
  the earlier contact-sheet label concern). Output `.hermes/evidence/defect_review/v1-0XX_hr.png`.
- `.hermes/evidence/stage2-v1-defect-scorecard.csv` — BLANK ordinal scorecard
  for the authoritative HUMAN second pass at 100-200% zoom.
- `.hermes/evidence/stage2-v1-defect-triage-proxy.md` — auxiliary-vision-proxy
  GROSS-triage flags only (LOW reliability; triage signal, not evidence).

Proxy gross-triage result: 0 gross/catastrophic defects flagged across 24
cases at HR-sheet resolution (consistent with 7-gate 24/24 accept). Highest
human-attention priorities (subtle-defect risk): v1-007 (drawn grip),
v1-011..014 (scabbard attachment), v1-019..021 (hand repair grip).
The proxy did NOT assign ordinal scores; the scorecard is pending the human pass.

STATUS: Step 1 IN PROGRESS — machine/triage layer done; the ordinal scorecard
awaits the user's human second pass (authoritative). No thresholds frozen yet.

## UNRESOLVED: PRIOR MANIFEST HASH `9f887646`
A prior hash `9f887646...` was raised as a possible earlier manifest hash.
Searched the locations expected to contain manifest hashes
(`.hermes/`, `.hermes/handoffs/`, and the Obsidian V1 note) for `9f887646`:
zero matches. The only manifest hash present anywhere in the evidence tree is
`4d610e2a...`. No artifact carrying `9f887646` was found, so no regeneration
or fixture-content change can be confirmed or denied from current evidence.
If a source shows `9f887646`, it is outside the searched locations and must be
supplied to trace any delta.

## CLAIM BOUNDARY (important)
The following are claims I made backed by artifacts I can read on the
filesystem; they are NOT facts you can independently establish from this chat:
- `REPORT_REGEN_OK` (I reran `stage2_validation.py` and it produced the report).
- `39 passed` (I reran the pytest suite; was 38, +1 collector-fallback test).
- `VERIFY_OK` over 99 artifacts (I ran the verifier).
These are reproducible: anyone with the repo can run the verifier command
recorded in the evidence manifest, but the chat text itself is my assertion.

Fresh verification:
- Validation + approval runner + refinement + render harness: 39 passed (was 38;
  +1 regression test for collector pending-provenance fallback).
- New/adjacent Python modules compile.
- V0 CLI regenerated schema-v3 HARNESS_VALIDATED report.
- V1 preflight: PREFLIGHT_PASS, 24 cases, 24 unique source hashes, class split
  verified; frozen manifest SHA-256
  `4d610e2a5100dc099ba63a110859cbd2c2ee54a50b177d9ce7a94808713dae93`.
- V1 runner dry-run: `DRY_RUN_READY_AWAITING_EXPLICIT_GPU_APPROVAL` (historical;
  execution completed 2026-07-26 under the frozen manifest approval record).
- V1 executed: 24/24 generated, reviewed, reported; schema-v3 report written.
- Evidence manifest: 99 artifacts, VERIFY_OK, bound to `4d610e2a...`.
- Host quirk: run validation CLI with `PYTHONPATH=` so `.venv-gpu` loads its
  own PIL instead of the incompatible Hermes-agent PIL binary.

## STAGE 2 V1 GOVERNANCE STATE (2026-07-27)
Independent review: COMPLETE. Hash binding: VALID. Semantic reconciliation:
COMPLETE (23/23 match; 18 fail / 5 pass / 1 excluded). Baseline eligibility:
TRUE (certified via `stage2-v1-audit-reviews/_validator_result.json`).
Production authorization: NOT GRANTED. Feature activation: UNCHANGED (flags off).
- Certified hashes: `review_records_sha256` `4bcca27d54b24c70df070d0ddcf94d793269bfd222758e1669acf5ae40d75b0c`;
  `summary_sha256_before_approval` `e862c35fb8b3b89fabb15696af8850438b31132d11ad976dfe77de58fe150783`.
- `baseline_eligible: true` = the evidence package passed the independent-review
  gate. It does NOT authorize production activation.
- BOUNDARY NOTE: the validator repairs (read-only mode, explicit 27-file digest
  set, separate `_validator_result.json`) are provenance of this certification.
  Because nothing was committed, the result is reproducible only while those local
  validator changes remain intact. Before another machine/branch/session relies on
  the gate, isolate + test + preserve the validator fix via normal change control.
  That preservation is separate from the independent-review decision and is NOT
  re-grading or production approval.
- Next decision is governance's: reject / bounded iteration / expand validation /
  separately-controlled limited-production evaluation. See
  `.hermes/evidence/stage2-v1-governance-state.md`.
