# EA-4E.92UK independent review of 92UJ

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY HOLD / NATIVE HOLD / PRODUCTION HOLD

One newly authorized independent read-only review inspected committed 92UJ
source at `eba9e56658c72e54e5893d7f75c8eb807333682f`. The reviewer found
that the six model files are hashed before container creation and rechecked
after the non-model probe, but the bind-mounted host directory is mutable
between those checks. The code does not hold a write-excluding handle or
otherwise prevent replacement during the mounted interval. The fake tests
cover preflight drift, not a swap during the mount. Therefore this candidate
must not be described as proving exact model bytes throughout the run.

The reviewer found the other source-level non-model gates sound: fixed
entrypoint flags, invalid-combination and inference-mode denial before Docker,
effective `json-file` and read-only mount checks before start, no HTTP path,
exact-owner cleanup, and fixed-category diagnostics. The requested Docker log
settings are not a hard disk or retention bound. The deadline is best-effort,
not a hard end-to-end limit if a CLI operation stalls. No tests or native
component were run by the reviewer. No container, model, GPU, receiver,
handoff, or production activation occurred in this review.

The one-review approval is consumed. The prior 92UJ candidate remains unrun.
Before any model-use claim, resolve the mutable-stage interval with an
evidence-backed immutable staging or write-exclusion mechanism and review it
independently. A separate exact one-shot authorization remains required for
any native non-model or model run. Production remains HOLD.
