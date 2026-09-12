# EA4F-2b - Director shot -> pose ControlNet at promo call site

**Flag:** `POSE_CONTROLNET_ENABLED` (default off)
**Call site:** `create_prompt_fallback_image` local_stable_diffusion branch
**Shot memory:** set in `make_chapter_image_prompts` when Visual Director returns a package

## Flow
1. VISUAL_DIRECTOR_ENABLED builds package with shots
2. remember_shots(pkg["shots"])
3. Later, create_prompt_fallback_image(index=N) with POSE_CONTROLNET_ENABLED=1
4. kwargs_for_generator(index=N) -> controlnet_* into create_local_stable_diffusion_image

## Fallback
If no remembered shot, prompt text heuristic (kneel/touch -> climax template).

## Rollback
Leave POSE_CONTROLNET_ENABLED unset/off.
