# EA-4E.87 Claim Conflict Regression

Parent: 7a1c091c329532290ec88311970aa386b167dcdc.
Scope: claim API exception translation, existing claim concurrency tests, this evidence.

Strengthened outcomes assertion includes captured thread results; 250-race different-claimant stress now requires the loser be conflict, not merely exactly one success. Existing file initially 29 passed; focused concurrency 4 passed, neither exonerated EA86 broad failure.

Added deterministic legal stale-initial-read case: winner durable claim committed, loser's first lookup misses as if before winner commit, atomic persistence sees winner. No database tamper. Pre-fix test failed with ExecutionAuthorizationConflictError from store.try_claim_authorization_atomically instead of declared ExecutionAuthorizationClaimConflictError. First new fixture attempt failed on non-Z timestamp and was corrected to existing clock contract before the production reproduction; no clock policy weakened.

Claim service now translates only ExecutionAuthorizationConflictError from atomic persistence into ExecutionAuthorizationClaimConflictError with chained cause. Store transaction, integrity, lifetime, policy, ownership and at-most-one semantics unchanged. Test verifies original winner, exactly one CLAIM_RECORDED event and integrity. The demonstrated route explains the broad ok/error signature, but does not retrospectively prove which exception occurred in the original nondiagnostic EA86 run.

Expanded Kilo/downstream ladder plus complete claim file requires working, staged and actual committed export qualification under unchanged fake-only/filesystem/report-host plugins and identical four selected OS durability exclusions. Companion Obsidian records exact results after verification. Full committed broad rerun remains required; no full-green or production-readiness claim.

No real receiver/model/activation/GPU/ComfyUI, no deletion, no unrelated changes. Historical broad HOLD evidence unchanged; missing genuine replay and raw restricted-boundary failures remain open.
