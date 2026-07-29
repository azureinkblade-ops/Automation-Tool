# Slice B0 — DETECTOR PREPROCESSING GATE (A' precondition)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Scope: narrow conditioning-image validation (option a), detector-produced map.

## What was built/run this step
- Installed controlnet_aux 0.0.10 + matplotlib into the CPU venv
  (detector runs on CPU; SDXL generation stays on the .venv-gpu runtime).
- pose_preprocessor.py: extract_openpose_condition(source, output) ->
  runs controlnet_aux.OpenposeDetector on an ordinary reference image,
  saves the detector's native pose map + a metadata sidecar
  (detector pkg/version, model repo, source image path + sha256, dims, ts,
  license note).
- Source reference: assets/pose_refs/sources/kneeling_man_candle_Shixart1985_CC-BY-2.0.jpg
  (real photo, CC BY 2.0, author Shixart1985 — attribution recorded).
- Derived map: assets/pose_refs/climax_kneel_detected_A.png
  (6.3 KB OpenPose visualization) + .pose_meta.json sidecar.
- Pose Resolver registry extended: template now points to (source + derived map);
  added resolve_pose_reference_enriched() carrying full provenance for the
  manifest evidence boundary (pose_condition_source=detector_output,
  pose_detector, pose_source_image, pose_source_sha256, pose_map_sha256,
  controlnet_model, controlnet_scale). Director remains FROZEN.

## Preprocessing gate result: FAIL (map must NOT reach SDXL)
The detector ran successfully and produced a single-person skeleton that meets
MOST of the gate:
  - one knee down ................................. PASS
  - other leg planted/foot forward ................ PASS
  - torso leaning ................................ PASS
  - one arm reaching downward ..................... PASS
  - no duplicate person .......................... PASS
  - no missing/disconnected principal limbs ...... FAIL
      * The figure is "shrouded in a blanket" (source description). The
        blanket occludes the LEFT arm: upper arm present (shoulder->elbow)
        but forearm/hand are detected as SEPARATE disconnected keypoints at
        the image bottom, with no connecting line to the elbow.
      * A merged keypoint is flagged (right wrist and right ankle share one
        dot) — an OpenPose artifact, anatomically impossible.
      * Minor false-positive noise dots near the right shoulder.

Per the user's explicit rule — "A malformed detector result should never
reach SDXL" — this map does NOT pass the gate. Therefore A'/B'/D'
were NOT run. The detector pipeline is validated as functional; the failure
is in the SOURCE image (occluded limbs), not in the detector or the
ControlNet checkpoint.

## Interpretation (bounded)
- The detector + controlnet_aux workflow executes correctly end to end.
- The leading hypothesis from the prior A-D isolation (hand-authored skeleton
  was distributionally wrong) is now refined: a REAL detector output is
  required, AND the source must have clearly-visible limbs. The blanket
  photo was a poor source choice for limb completeness.
- This is NOT yet evidence about whether the xinsir ControlNet transfers
  pose from a CORRECT map. That question remains open until a clean
  (limb-complete) detector map is produced and A' is run.

## Next concrete step (requires user decision / a new source)
To run A'/B'/D' validly, supply a KNEELING SOURCE with visible,
unoccluded limbs (e.g. a classical sculpture photo in the public domain,
or a clearly-posed sports/proposal photo under a permissive license).
Re-run pose_preprocessor.py on it; re-apply this preprocessing gate; only
if the map passes ALL six checks does it feed A'/B'/D'.

Candidates considered and why not used yet:
- Wikimedia "Category:Kneeling" is mostly blanketed/occluded or video
  frames (e.g. Astronaut Charles Duke — lunar EVA, poor pose ref).
- A public-domain kneeling STATUE photo is the strongest clean source
  (unambiguous, unoccluded limbs) but a verified PD file has not yet
  been selected/fetched. That selection is left explicit (licensing review)
  rather than auto-scraped.

## Evidence boundary preserved
The derived map carries a .pose_meta.json sidecar recording exactly which
source + detector produced it, so a future run cannot silently switch
between hand-authored and detector maps. Scaffold remains env-gated OFF.
