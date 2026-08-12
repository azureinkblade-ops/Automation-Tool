---
title: "AUTH-2026-08-12 Hermes First Real Governance Consumer"
document_id: "AUTH-2026-08-12-HERMES-GOVERNANCE-CONSUMER"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
---

# AUTH-2026-08-12 Hermes First Real Governance Consumer

This authorization permits the first narrow production-facing consumer of the
Hermes deterministic governance runtime, following `HERMES_RUNTIME_INTEGRATION_PLAN.md`
and the First Real Governance Consumer milestone authorization.

## Authorized scope

1. Add `tools/hermes_core/governance_consumer.py` with `get_task_governance_status(task_id)`
   and a frozen `TaskGovernanceStatus` dataclass (`task_id`, `governance_state`,
   `accepted`, `can_authorize_execution`).
2. Export `CAN_AUTHORIZE_EXECUTION`, `TaskGovernanceStatus`, `get_task_governance_status`
   from `tools/hermes_core/__init__.py`.
3. Add `tests/hermes_core/test_governance_consumer.py`.
4. Update `docs/architecture/hermes-governance-runtime.md`.

## Explicit non-scope (preserves Phase 6 + runtime boundary)

- No worker launch, no work enqueue, no execution invocation.
- No `ExecutionAuthorization` artifact, no execution-authority service.
- No `AWAITING_EXECUTION_AUTHORIZATION` / `AUTHORIZED` / `EXECUTING` states.
- `can_authorize_execution` is a hard `False` declaration, never derived from
  state.
- No `app.py` change (AGENTS.md single-writer rule).
- `automation_state.db` remains unrelated; no cross-store merge.

## Verification requirements

- 5 new consumer tests pass; full Hermes core suite green (278).
- Integrity tampering fails closed (`GovernanceIntegrityError` propagates).
- No execution side effects in tests.
- `git diff --check` clean; unrelated `main` edits untouched.
