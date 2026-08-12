---
title: "AUTH-2026-08-12 Hermes Governance Consumer Integration Proof"
document_id: "AUTH-2026-08-12-HERMES-GOVERNANCE-CONSUMER-INTEGRATION"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
---

# AUTH-2026-08-12 Hermes Governance Consumer Integration Proof

This authorization permits integrating the read-only governance consumer into
one real, existing task/review orchestration path, following the First Real
Governance Consumer milestone (`209492c`) and the
`Hermes Governance Consumer Integration Proof Milestone` authorization.

## Authorized scope

1. Enrich `tools/hermes_core/review_runner.py` `ReviewRunnerResult` with a
   read-only `governance` field (`TaskGovernanceStatus`) populated by
   `get_task_governance_status(task_id)` inside `ReviewRunnerStub.prepare()`.
2. Add `tests/hermes_core/test_review_runner_governance_integration.py`.
3. Update `docs/architecture/hermes-governance-runtime.md`.

## Explicit non-scope (preserves Phase 6 + runtime + consumer boundary)

- No execution authorization.
- No worker launch.
- No worker enqueue.
- No AUTHORIZED state.
- No EXECUTING state.
- No AWAITING_EXECUTION_AUTHORIZATION state.
- No app.py modification unless separately held and approved.
- No automation_state.db coupling.

The integration is observational only. `ACCEPTED` remains governance acceptance,
never execution permission. `can_authorize_execution` stays hard-False; the
negative-authority mutation `can_authorize_execution = governance.accepted`
breaks the integration test. Integrity failures propagate as
`GovernanceIntegrityError` (fail-closed).

## Verification requirements

- 6 integration tests pass; existing consumer + review_runner tests green; full
  Hermes core suite >= 284.
- No forbidden execution terms in production `review_runner.py`.
- `git diff --check` clean; no production governance DB tracked.
- Unrelated `main` edits untouched.
