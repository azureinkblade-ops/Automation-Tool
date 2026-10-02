# EA4F-2 - Pose + ControlNet integration cleanup

**Lane:** `feature/ea4f-regional-hand-repair-pilot`  
**Checkpoint base:** `496d52f`  
**Status:** IN PROGRESS  
**Type:** Pose registry hygiene + ControlNet CLI wiring + pure helper module

## Intent

Close the gap between:
1. `pose_resolver` (registry + provenance)
2. `local_image_generator` (already supports ControlNet CLI)
3. `create_local_stable_diffusion_image` in app.py (tests expected kwargs; implementation was incomplete)
4. Visual Director (semantic pose only; must stay free of ControlNet mechanics)

## Must

- Pass ControlNet kwargs from app into generator CLI only when model + image both present
- Align registry production map (map C) with unit tests
- Provide pure `pose_conditioning` helpers for shot -> kwargs / CLI args
- Keep visual_director free of torch and ControlNet imports

## Must NOT

- Rewrite Visual Director prompt freeze
- Broad app.py cleanup
- Force ControlNet on every render (opt-in via kwargs or env)

## Delivered in this slice

- [x] `create_local_stable_diffusion_image` accepts controlnet_* kwargs and appends CLI args
- [x] `pose_conditioning.py` pure helper
- [x] tests/test_pose_conditioning.py
- [x] test_pose_resolver map assertion updated to production map C
- [ ] Director shot path auto-resolves pose via pose_conditioning (optional follow-up; leave behind flag)
- [ ] Document env vars in README or hermes plan (follow-up)

## Env vars (existing)

- `LOCAL_SD_CONTROLNET_MODEL` (default xinsir/controlnet-openpose-sdxl-1.0 when using helper)
- `LOCAL_SD_CONTROLNET_SCALE` (0.65)
- `LOCAL_SD_CONTROL_GUIDANCE_START` (0.0)
- `LOCAL_SD_CONTROL_GUIDANCE_END` (0.75)

## Example call

```python
from pose_conditioning import resolve_conditioning_for_shot

shot = {"type": "climax", "action": "kneeling, touching"}
cn = resolve_conditioning_for_shot(shot)
# strip enrichment before spreading into generator
enrich = cn.pop("pose_enrichment", {})
create_local_stable_diffusion_image(prompt, target, seed=seed, **{
    k: v for k, v in cn.items() if k.startswith("control")
})
```

## Rollback

- ControlNet remains off unless kwargs or env model+image are provided
- Revert this commit if CLI wiring misbehaves
