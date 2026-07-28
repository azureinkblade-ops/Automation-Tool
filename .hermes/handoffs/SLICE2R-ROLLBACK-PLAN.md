# Slice 2R — Rollback Plan (Design, recorded)

**Part of:** `SLICE2R-AIVSB-INJECTION-BOUNDARY-REMEDIATION` (RECORDED design; implementation not authorized)

## Corrected safety statement
Reverting Slice 2R is mechanically straightforward but is **NOT operationally safe if
the feature flag has ever been enabled outside isolated tests.** The pre-Slice-2R state
(line 1264–1273) CONTAINS the confirmed leak. Therefore:

> Rollback is permitted ONLY while `ENABLE_AIVSB_RETRIEVAL` remains OFF.
> If the flag has EVER been enabled outside isolated test environments, rollback must
> FIRST disable the flag and verify that no public output can contain retrieved context
> before the revert is considered safe.

## Rollback triggers
- Any AC-1 leak test fails (boundary broken).
- AC-2 outcome proof fails (block does not reach private composition).
- AC-3 public-schema regression.
- `tests/test_promo_copy.py` characterization fails.
- Unexpected interaction discovered.

## Procedure (git-based, no force)
1. Confirm `ENABLE_AIVSB_RETRIEVAL` is OFF in `main`/production (and has never been ON
   outside isolated tests). If unsure, disable the flag first and re-verify no public
   output can contain retrieved context.
2. `git revert <slice2r_commit>` (new revert commit; preserves history; no `--amend`,
   no force). Revert is preferred for auditability over partial checkout.
3. Re-run T1/T2/T3/T8/T9 to confirm: finals clean, public schema unchanged, OFF identity
   restored, app.py parity holds.
4. Do NOT push the revert without separate authorization.

## Why the revert is mechanically clean
- No `automation_db` schema change (Slice 2R touches no tables).
- No change to `retrieve()`/`provenance`/`dynamic_cta_goal`; index and runs unaffected.
- Only `promo_copy.py` (signal type + helper refactor + call-site + `style` selection) is reverted.

## Operational caveat (carried forward)
If the flag was enabled in any non-isolated environment, the revert restores the leaking
state. The governance owner must treat that as a separate incident (verify/clean any
public outputs) before relying on the revert as "safe."
