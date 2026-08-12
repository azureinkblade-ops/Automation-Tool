---
title: "AUTH-2026-08-12 Hermes Governance Runtime Integration"
document_id: "AUTH-2026-08-12-HERMES-RUNTIME-INTEGRATION"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
---

# AUTH-2026-08-12 Hermes Governance Runtime Integration

This authorization permits a tightly scoped runtime wiring seam that lets
application/runtime code obtain and use the authoritative Hermes governance
store, following the approved `HERMES_RUNTIME_INTEGRATION_PLAN.md`.

## Authorized scope

1. Add `tools/hermes_core/runtime_config.py` resolving the production governance
   DB path: `HERMES_GOVERNANCE_DB` override → `%LOCALAPPDATA%\Hermes\governance.db`.
2. Add `tools/hermes_core/runtime.py` providing `get_governance_store()` (the
   single construction seam), lifecycle close, and a read-only query surface
   (`get_governance_chain`, `get_governance_state`, `verify_governance_integrity`,
   `is_governance_accepted`).
3. Export the runtime API from `tools/hermes_core/__init__.py`.
4. Add `tests/hermes_core/test_governance_runtime_config.py` and
   `tests/hermes_core/test_governance_runtime.py`; document the design in
   `docs/architecture/hermes-governance-runtime.md`.

## Explicit non-scope (preserves Phase 6 boundary)

- No `app.py` modification is required or authorized by this milestone; the seam
  is ready for a future first consumer without changing the monolith.
- No worker execution, no execution authorization, no `AUTHORIZED`/`EXECUTING`
  transitions.
- No governance tables in `automation_state.db`; the two stores remain separate.
- No `.db`/`.db-wal`/`.db-shm` may be committed; the governance DB stays runtime
  state.

## Verification requirements

- 21 new runtime tests pass; full Hermes core suite green (273).
- 8/8 runtime integration mutants have teeth; source restored byte-exactly.
- Ad-hoc override probe passes and removes its temporary DB.
- `git diff --check` clean; unrelated `main` edits untouched.
