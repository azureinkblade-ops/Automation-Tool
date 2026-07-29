# Proposal: Per-novel data-driven video motion (Tiers A, B, C)

Status: PROPOSED. Not applied. For review by the app.py lane owner / approving
session before any edit. No app.py lines were modified to create this doc.

## Intent
Extend the existing TikTok/Reel video renderer so the *animations chosen are
decided by which novel (abbr) is being portrayed*, instead of one hardcoded
zoompan push-in for every slide. Uses only free, local, already-installed
ffmpeg filters (Tiers A camera, B effects, C transitions). AnimateDiff / true
character motion (Tier D) is DEFERRED (user directive) and out of scope here.

## Scope boundaries (do / do not)
DO:
- Add a per-novel motion profile table.
- Thread `abbr` into the renderer so the profile is selectable.
- Replace the hardcoded zoompan string with profile-driven motion per shot.
- Add ffmpeg effect-chain (grain/vignette/bloom/grade/fog) per profile.
- Replace plain concat with profile-selected `xfade` transitions.
- Keep a `None`/unknown-abbr fallback that reproduces CURRENT output (no regression).

DO NOT:
- Touch AnimateDiff / LTX / Wan (Tier D). Deferred by user.
- Change audio mixing, narration, CTA logic, or overlay text rendering.
- Change the two-renderer funnel (both call write_animated_reel_builder_script).
- Touch shared mutable state outside this function and its helpers.

## Verified existing architecture (read-only, for reviewer confidence)
- 4 novels: EN=Eternal Nexus, HA=Heavenly Ascension System, SF=Soul Forge Era,
  HP=Hundredfold Path. Map at app.py:278-283 (NOVEL_NAMES).
- Both renderers funnel into ONE template builder:
  - write_tiktok_video_helper        -> app.py:15524 (normal pack)
  - write_deep_tiktok_video_helper    -> app.py:15785 (deep pack) -> calls the
    same write_animated_reel_builder_script with deep=True.
  - write_animated_reel_builder_script -> app.py:15203-15495. This writes a
    per-folder make_tiktok_video.py and runs it.
- Current motion already present (so this is an EXTENSION, not greenfield):
  - zoompan push-in z up to 1.075 (normal) / 1.05 (CTA): app.py:15425-15427,
    15450-15451.
  - fade in/out 0.35s: app.py:15427, 15453.
  - drawtext captions: app.py:15432-15437.
  - plain concat + audio duck: app.py:15469-15472.
  - Two render paths: render_with_moviepy (primary) and
    render_with_ffmpeg_fallback (the one used in practice per inline comment).
- abbr availability:
  - Deep path: abbr comes from metadata (rebuild_deep_tiktok_video_from_metadata
    app.py:5954-5985). NOT yet passed to write_deep_tiktok_video_helper -> must
    be threaded.
  - Normal path: write_tiktok_video_helper called at app.py:12649 and 15189
    WITHOUT abbr. Must add abbr param and pass it at both call sites.

## Proposed code changes (concrete, not yet applied)

### 1. Module-level motion profile table (add near app.py:283, after NOVEL_NAMES)
PROPOSED (illustrative). Motion entries are from the VERIFIED vocabulary in 2b
(push_in/pull_out/pan_left/pan_right/tilt_up/tilt_down/crash_zoom/arc_rotate/
parallax). Indexed by shot position (0=opening hook, 1=escalation, 2=mid,
3=closing; modulo wrap on mismatch):
```
MOTION_PROFILES = {
    "EN": {  # Eternal Nexus: cosmic/sect, expansive
        "shot_motion": ["push_in", "pan_left", "arc_rotate", "pull_out"],
        "effects": ["bloom", "fog", "grade_cool"],
        "transition": "dissolve",
    },
    "HA": {  # Heavenly Ascension System: ascension, ethereal
        "shot_motion": ["tilt_up", "pull_out", "arc_rotate", "tilt_down"],
        "effects": ["vignette", "chromashift", "grade_ethereal"],
        "transition": "fadegrays",
    },
    "SF": {  # Soul Forge Era: forge/fire/armor, intense (inspected sample)
        "shot_motion": ["crash_zoom", "pan_right", "parallax", "crash_zoom"],
        "effects": ["embers", "flicker", "grain_strong", "grade_warm"],
        "transition": "fadewhite",
    },
    "HP": {  # Hundredfold Path: structured progression
        "shot_motion": ["push_in", "pan_left", "push_in", "pull_out"],
        "effects": ["grade_clean", "vignette"],
        "transition": "coverleft",
    },
}
```
Note: "parallax" routes to the OpenCV+MiDaS backend (sf_proto/animate_scene.py)
and is the only non-zoompan move; reserve for hero shots.

### 2. Helper (add near the profile table)
PROPOSED:
```
def motion_plan_for(abbr, shot_index, total_shots):
    profile = MOTION_PROFILES.get((abbr or "").upper())
    if not profile:
        return {"motion": "push_in_default", "effects": [], "transition": "fade"}
    motions = profile["shot_motion"]
    motion = motions[shot_index % len(motions)]
    return {
        "motion": motion,
        "effects": profile["effects"],
        "transition": profile["transition"],
    }
```

### 2b. Camera-move vocabulary (VERIFIED to render on the real SF sample,
ffmpeg 8.1.2, first-vs-last-frame diff measured > 5/255 = real motion):
- push_in     : zoompan z up to 1.075 (baseline, already in code)
- pull_out    : zoompan z from 1.12 down to 1.0
- pan_left    : zoompan x drifts right over time
- pan_right   : zoompan x drifts left over time (mirror of pan_left)
- tilt_up     : zoompan y drifts up over time
- tilt_down   : zoompan y drifts down over time (mirror of tilt_up)
- crash_zoom  : zoompan z quadratic ease-in punch (accelerating)
- arc_rotate  : ffmpeg `rotate='0.04*(t/TOTAL)':c=black` THEN zoompan
                (IMPORTANT: rotate must come BEFORE zoompan in the filter
                 chain; chaining zoompan->rotate fails with "no packets").
- parallax (depth): NOT a zoompan move. Uses the standalone OpenCV+MiDaS
  module (sf_proto/animate_scene.py) to separate foreground/background and
  shift near layers more than far. This is the one motion zoompan CANNOT do.
  Wire as backend="depth" in the motion planner; only for hero shots (cost).
Measured diffs (3s clips, 1080x1920): push_in 20.6, pull_out 15.6,
pan_left 29.8, tilt_up 30.5, crash_zoom 16.0, arc_rotate 17.4. All REAL.

### 3. Thread abbr into the two helpers + builder
- write_tiktok_video_helper signature (app.py:15524): add
  `abbr: str | None = None`. Pass through to write_animated_reel_builder_script.
- Call sites app.py:12649 and app.py:15189: pass `abbr=abbr` (source abbr is
  available in those call contexts already; confirm at edit time).
- write_deep_tiktok_video_helper (app.py:15785): add `abbr` param, pass
  `abbr=abbr` into write_animated_reel_builder_script. Caller
  rebuild_deep_tiktok_video_from_metadata already has abbr (app.py:5979).
- write_animated_reel_builder_script (app.py:15203): add `abbr: str | None = None`.
  Compute `motion_plans = [motion_plan_for(abbr, i, len(images)) for i in
  range(len(images))]` and embed into the generated script as a literal list.

### 4. In the generated make_tiktok_video.py template
Replace the hardcoded zoompan draw string (app.py:15424-15427) with a
motion-driven builder:
- push_in       -> current zoompan (keep)
- pull_out      -> zoompan z from 1.075 down to 1.0
- pan_left/right-> zoompan with x offset drift
- tilt_up/down  -> zoompan with y offset drift
- dolly_zoom    -> zoompan z increase + slight reverse pan (Vertigo approx)
- crash_zoom    -> faster zoompan ease-in (larger z step)
- push_in_default -> exact current behavior (fallback, no regression)
- parallax      -> routes to backend="depth" (OpenCV+MiDaS, sf_proto/animate_scene.py)
- animatediff   -> routes to backend="animatediff" (PHASE 2, see below). When a
  shot's motion_plan selects "animatediff", the per-folder render should call
  the AnimateDiff worker instead of the ffmpeg zoompan chain for THAT clip, then
  hand the produced mp4 back into the concat/xfade stage. Keep zoompan/xfade as
  the default so only hero shots invoke the GPU worker.
Append effects per plan["effects"] as ffmpeg filters:
- grain(_strong) -> noise
- vignette      -> vignette
- bloom         -> gblur + blend screen
- fog / embers  -> perlin (noise gen) + overlay + opacity animation
- chromashift   -> chromashift
- grade_*        -> eq / curves / colorlevels per novel look
Replace plain concat (app.py:15469-15471) with xfade between consecutive clips
using plan["transition"] (xfade modes verified present in ffmpeg 8.1.2:
fade, dissolve, fadewhite, fadegrays, coverleft, reveal*, slide*, etc.).

### 5. MoviePy path (app.py:15354-15413) - mirror minimally or leave
Primary path is ffmpeg fallback in practice. To limit scope, apply the motion
selection to the ffmpeg fallback first; mirror into render_with_moviepy make_frame
zoom/pan only if the approving authority wants both paths consistent. Flag this
as a known partial-coverage item.

## What must be verified before declaring done (evidence discipline)
1. Build one pack per novel (EN/HA/SF/HP). For each, inspect the generated
   make_tiktok_video.py to confirm motion_plans embedded and non-default for
   known abbr.
2. Run the generated script; confirm ffmpeg exit 0 and tiktok-video.mp4 exists
   with duration ~ target (normal ~23s, deep ~71s).
3. Measure motion: first-vs-last frame mean abs diff per clip > ~10/255
   (proves not static). Reuse the diff check from the depth-2.5D prototype.
4. Confirm transitions rendered: scene-cut count (ffmpeg scene detect) is
   HIGHER than the current ~2-3 for a 71s video (xfade adds cuts).
5. Regression: a pack built with abbr=None reproduces output byte-similar to
   current (or within tolerance) -> proves fallback works.
6. No new em dashes in any file/path/CLI value (AGENTS.md rule).

## Out of scope but flagged (separate concern, not in this change)
- IP risk: the SF sample (sf-nh3) opening/mid frames show a sword-throne
  strongly resembling Game of Thrones Iron Throne. This is a PROMPT/content
  issue, not an animation-code issue. Recommend a separate pass to audit
  tiktok-posts for copyrighted-iconography before next batch. Not part of this
  motion proposal.
- Tier D (AnimateDiff TRUE character motion) is DEFERRED from Phase 1 but is
  now VERIFIED-RUNNABLE on this host. See PHASE 2 section below for the
  evidence, the base-model requirement, and the backend="animatediff" design.
  Key new fact: .venv-gpu (torch 2.11.0+cu128, CUDA TRUE, RTX 4080 SUPER)
  runs AnimateDiff; the HERMES venv is CPU-only and cannot. The .venv-gpu python
  is reached only if PYTHONPATH is UNSET (it otherwise re-routes into hermes
  venv and fails torch load).

## Files touched (proposed)
- app.py: NOVEL_NAMES area (~283), write_tiktok_video_helper (~15524),
  write_deep_tiktok_video_helper (~15785), write_animated_reel_builder_script
  (~15203-15495), call sites (12649, 15189), rebuild_deep (5979 pass-through).
- No new files required (logic lives in app.py + generated per-folder script).

## Handoff requirement (AGENTS.md)
This change touches app.py (shared monolith). Before any edit, the app.py lane
owner must confirm clean tree + provide commit hash. This doc is the proposal;
the implementing session must open its own handoff note recording intent, diff
regions, and a guard statement ("must not alter audio/narration/CTA/overlay
text"), then declare complete only after the verification steps above pass.

## PHASE 2 (deferred, Tier D) - AnimateDiff TRUE character motion
VERIFIED-RUNNABLE on this host as of 2026-07-25. Not part of Phase 1.

### Evidence (actual test run, not assumption)
- Host GPU: NVIDIA RTX 4080 SUPER, CUDA TRUE via .venv-gpu
(torch 2.11.0+cu128, diffusers 0.39.0).
- Ran AnimateDiffVideoToVideoPipeline image-to-video on the real SF sample
(sf_proto/sample_src.png) using:
- motion adapter: guoyww/animatediff-motion-adapter-v1-5-2 (SD1.5 module)
- base: SG161222/Realistic_Vision_V5.1_noVAE (SD1.5, downloaded)
- 16 frames, 20 steps, strength=0.7, seed=42.
- Result: produced animatediff_test.mp4. Generation step = 11.7s for 16
frames on the 4080 SUPER (fast). First-vs-last-frame diff = 6.11/255
(real but subtle motion; strength=0.7 intentionally preserves source).
- Test scripts: sf_proto/test_animatediff_sd15.py (working),
sf_proto/test_animatediff.py (SDXL attempt, blocked - see bug below).

### Why it is NOT yet production-usable for Azure Inkblade (evidence)
1. WRONG BASE MODEL / STYLE DRIFT. The SD1.5 realism base produced the wrong
 aesthetic (generic photoreal, not manhwa/SDXL). Vision inspection of the
 output frames found: (a) subject stays in static seated pose - no visible
 cloth billow / fire flicker / posture shift; the 6.11 diff is mostly
 lighting/shading drift, not coherent character motion; (b) hallucinated
 gibberish text on the character ("GVIIT TUDEE GDD"); (c) fused/blurry hands.
 For novel promo this is below the bar - it must use YOUR character style.
2. SDXL v2v PATH BROKEN in diffusers 0.39.0. Using your local SDXL base
 (models/sdxl-base) + guoyww/animatediff-motion-adapter-sdxl-beta hits:
 TypeError: argument of type 'NoneType' is not iterable
 at unet_motion_model line `if "text_embeds" not in added_cond_kwargs`.
 The SDXL-beta adapter works for TEXT-to-video (AnimateDiffSDXLPipeline) but
 the VIDEO-to-VIDEO path has a conditioning bug here. So "animate MY still
 with SDXL" is not working yet.
3. CHARACTER CONSISTENCY RISK. AnimateDiff can drift face/design frame-to-frame,
 which fights the "same protagonist" goal. Needs IP-Adapter or a character
 LoRA locked during generation. Not yet built.

### Required before Phase 2 activation (gates)
- [ ] Use the CORRECT base: either (a) fix the SDXL v2v bug so your local
    SDXL base + manhwa LoRA drives AnimateDiff, or (b) obtain a manhwa-style
    SD1.5 checkpoint/LoRA and feed it into the working v2v path.
- [ ] Lock character identity (IP-Adapter / character LoRA) so frames stay
    consistent with the source still.
- [ ] Re-measure: target first-vs-last diff with VISIBLE coherent motion
    (cloth/fire/pose), not just shading drift; vision-confirm no gibberish
    text and no hand deformation.
- [ ] Resolve the .venv-gpu PYTHONPATH trap: Phase 2 must invoke the worker
    with PYTHONPATH UNSET or a fully isolated interpreter, else it silently
    falls back to CPU and fails.
- [ ] Decide hero-shot-only policy: AnimateDiff is GPU-heavy; restrict to the
    per-novel "animatediff" slot in MOTION_PROFILES (hero shots), not every
    clip. Pipeline load was ~401s one-time (download/cache); steady-state
    gen ~12s/16 frames - acceptable for a few hero shots per video.

### backend="animatediff" design (swapper)
motion_plan_for() may return motion="animatediff" for a shot (hero slot).
The per-folder make_tiktok_video.py template already branches on
plan["motion"] (see PHASE 1 section 4). For "animatediff":
- call an external worker (sf_proto/animate_scene.py extended, or a new
  animatediff_worker.py) that runs the .venv-gpu AnimateDiff pipeline,
- returns a clip mp4,
- that clip is dropped into the same concat/xfade stage as ffmpeg clips.
This keeps the swap modular: backend="depth" | "ffmpeg" | "animatediff".
Phase 1 ships "depth" + "ffmpeg"; "animatediff" is wired but gated OFF until
the gates above are met.
