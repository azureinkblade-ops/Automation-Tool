# EA4F-1 - Hand mask stub

**Module:** `hand_repair/mask_stub.py`
**Flag:** `HAND_REPAIR_AUTO_MASK` (default off)

When HAND_REPAIR_ENABLED=1 and no mask_path is provided:
- If HAND_REPAIR_AUTO_MASK=1, generate a coarse lower-third / region mask
- Else reject with clear reason

This is intentionally not a real hand detector. Replace ensure_mask_for_source
internals later without changing HandRepairService public API.
