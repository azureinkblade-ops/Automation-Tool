# EA4F-1 - Hand Repair Service Boundary

**Lane:** `feature/ea4f-regional-hand-repair-pilot`  
**Checkpoint base:** `263258a1d421f5f8d6ca518bfa2fe1afd9079bb5`  
**Slice ID:** EA4F-1  
**Status:** READY FOR IMPLEMENTATION  
**Owner:** (claim this lane)  
**Date opened:** 2026-09-07  
**Type:** Isolated module extraction + public service boundary  
**Touches `app.py`?** Only a thin, final wiring commit (after this slice is green)

---

## Intent (dual-mode handoff)

**What we are building**  
A clean, self-contained **Hand / Regional Repair Service** that sits on top of the existing `object_refinement.py` engine. It owns hand-specific prompts, acceptance rules, and the public API that Visual Director and the promo pipeline will call.

**Why**  
- The current regional hand repair pilot must not grow more logic inside `app.py`.  
- `object_refinement.py` is already an excellent pure CPU orchestration layer. We protect it and put domain policy (hands) in a dedicated service.  
- This creates a permanent, testable boundary that future slices (pose, full-body, face, etc.) can reuse.

**What this slice must and must not alter**

| Must | Must NOT |
|------|----------|
| Create `hand_repair/` package with public API | Modify `app.py` until the very last thin wiring commit |
| Keep `object_refinement.py` free of hand-specific policy | Import `app` from any new module |
| Preserve the outside-mask pixel gate | Change provenance schema without a version bump |
| Feature-flag the whole path (`HAND_REPAIR_ENABLED=0` by default) | Broad formatting or unrelated cleanup |
| Characterization + unit tests before any wiring | Touch Visual Director prompt freeze logic |

---

## Public Contract (frozen for this slice)

```python
# hand_repair/service.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

@dataclass(frozen=True)
class HandRepairRequest:
    source_path: Path
    region: str = "hands"               # "hands" | "left_hand" | "right_hand" | "both"
    prompt: Optional[str] = None        # None -> use default hand-repair prompt bank
    negative_prompt: Optional[str] = None
    strength: float = 0.25
    seed: Optional[int] = None
    mask_path: Optional[Path] = None    # if None, service may generate a coarse mask later
    guide_path: Optional[Path] = None

@dataclass(frozen=True)
class HandRepairResult:
    status: str                         # "accepted" | "rejected" | "pending_review" | "disabled" | "error"
    output_path: Path
    candidate_path: Optional[Path] = None
    provenance_path: Optional[Path] = None
    diff_path: Optional[Path] = None
    reasons: Tuple[str, ...] = ()

def repair_hands(request: HandRepairRequest, work_dir: Path) -> HandRepairResult:
    """Public entry point. Feature-flagged. Never raises into the caller for normal reject paths."""
    ...
```

---

## File layout for this slice

```
hand_repair/
  __init__.py                 # re-exports repair_hands, HandRepairRequest, HandRepairResult
  service.py                  # orchestration + public API
  prompts.py                  # hand-specific prompt bank
  acceptance.py               # hand-specific acceptance rules (optional thin layer)
tests/
  test_hand_repair_service.py
  test_hand_repair_imports.py # fresh-process import test (no app import)
```

Existing files that may be lightly touched (only for wiring or import hygiene):

- `object_refinement.py` (read-only preferred; only if a tiny generic hook is needed)
- `local_object_refiner.py` (fix the `import app` smell - see Step 1)
- `app_config.py` (add two feature flags)
- `app.py` (final thin call site only, after everything else is green)

---

## Implementation Steps (ordered)

### Step 0 - Claim ownership and safety
1. Update `AGENTS.md` "Current lane ownership" (or leave a clear note in this handoff) that this session owns the hand-repair lane.
2. Confirm working tree is clean relative to `263258a1`.
3. Create this handoff file (already done by creating this document).

### Step 1 - Clean `local_object_refiner.py` import boundary
- Remove the bare `import app` that exists only for DLL / path setup.
- Extract the minimum path/DLL setup into a shared helper (e.g. `gpu_runtime.py` or reuse existing local_image_generator helpers).
- Goal: `local_object_refiner` must not import the monolith.

### Step 2 - Create package skeleton + public API
- Create `hand_repair/__init__.py`, `service.py`, `prompts.py`.
- Implement `repair_hands` so that when `HAND_REPAIR_ENABLED` is off it immediately returns `status="disabled"` and the original image.
- When enabled, it builds a `RefinementRequest` and calls `ObjectRefinementService`.

### Step 3 - Feature flags in `app_config.py`
```python
HAND_REPAIR_ENABLED = os.getenv("HAND_REPAIR_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
HAND_REPAIR_AUTO_ACCEPT = os.getenv("HAND_REPAIR_AUTO_ACCEPT", "0").strip().lower() in {"1", "true", "yes", "on"}
```

### Step 4 - Tests (must be green before any app.py change)
- `tests/test_hand_repair_imports.py` - fresh subprocess import of `hand_repair` succeeds and does **not** import `app`.
- `tests/test_hand_repair_service.py`:
  - disabled path returns original image
  - outside-mask change gate still rejects
  - provenance file is written with schema_version and status
  - default prompt bank is used when prompt=None

### Step 5 - Thin wiring into `app.py` (only after Steps 1-4 are green)
- Single call site after main image generation (behind the feature flag).
- Follow full AGENTS.md handoff protocol.
- Commit is isolated: no formatting, no unrelated cleanup.

### Step 6 - Verification and declare
- Run regression smoke.
- Update this handoff with the final commit hash.
- Declare handoff complete only after the checklist below is satisfied.

---

## Acceptance Checklist (before declaring done)

- [ ] `hand_repair` package exists and is importable without importing `app`
- [ ] `local_object_refiner.py` no longer imports `app`
- [ ] Feature flags default to **off**
- [ ] Outside-mask pixel preservation gate still enforced
- [ ] Provenance schema remains compatible with existing Stage-2 records
- [ ] Unit + import tests pass
- [ ] No broad cleanup committed with the functional change
- [ ] Final wiring commit in `app.py` is tiny and isolated
- [ ] This handoff note updated with the commit hash that completes the slice

---

## Rollback plan

- Feature flag off -> path is completely inert.
- If the thin `app.py` wiring causes issues, revert only that single commit; the service remains available for later re-wiring.
- No schema migration is performed in this slice, so no data migration rollback is required.

---

## Related existing assets (do not rewrite)

- `object_refinement.py` - generic CPU engine (keep pure)
- `local_object_refiner.py` - SDXL inpainting backend
- `pose_resolver.py` - pose template registry (future EA4F-2)
- `visual_director.py` - owns semantic pose intent (do not put repair logic here)
- `.hermes/plans/2026-07-16_143000-monolith-extraction.md` - larger extraction plan; this slice is a parallel low-risk lane

---

## Em-dash rule reminder
No em dashes in commit messages, file names, or machine-parsed strings.

---

**Next slice after this one:** EA4F-2 (Pose + ControlNet integration cleanup) once hand repair is stable behind the flag.

---

## Progress log

| Commit | What |
|--------|------|
| `61bc0cc2f4a27a40ce3f1cd394082b37540e32e5` | Skeleton package + tests + this handoff |
| (this commit) | C1 gpu_runtime + clean local_object_refiner; C2 app_config flags; C3 integration helper (wiring example, no app.py edit); C4 AGENTS ownership note |

### app.py wiring example (not applied yet - still flag-off and mask-required)

After a main promo image is written to `image_path`:

```python
from hand_repair.integration import maybe_repair_hands

image_path = maybe_repair_hands(
    source_path=image_path,
    work_dir=Path(campaign_dir) / "hand-repair",
    mask_path=hand_mask_path,  # required in EA4F-1
    region="hands",
)
```

Do not land the `app.py` call site until Step 1-4 tests are green on the machine and a single writer claims the monolith lane.

### Update: app.py thin wiring applied
See `.hermes/handoffs/EA4F-1-APP-WIRING-PATCH.md`.
Flag default remains off; requires HAND_REPAIR_MASK_PATH when enabled.
