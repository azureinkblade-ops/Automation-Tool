# EA4F-1 Step 5 - app.py wiring patch (applied)

**Checkpoint base:** `496d52f`  
**Applied on branch:** `feature/ea4f-regional-hand-repair-pilot`  
**Touches:** `app.py` function `create_local_stable_diffusion_image` only

## Intent

One thin, flag-gated post-hook after successful local SD generation. Default is fully inert.

## Contract

- Requires `HAND_REPAIR_ENABLED=1` (or app_config equivalent)
- Requires `HAND_REPAIR_MASK_PATH` pointing to an existing mask PNG
- Optional `HAND_REPAIR_REGION` (default `hands`)
- On success: copies repaired image over `target`, records `metadata["handRepair"]`
- On any error: original image kept; error string in metadata (no raise)

## Diff region signature

- Function: `create_local_stable_diffusion_image`
- Inserted after metadata.setdefault block, before `return metadata`
- Must not alter prompt freeze, provider priority, or non-local SD paths

## Must NOT

- Broad formatting of app.py
- Import hand_repair at module top level
- Run when flag is off
- Invent a mask when HAND_REPAIR_MASK_PATH is unset

## Rollback

Revert this commit, or leave `HAND_REPAIR_ENABLED=0` (default).
