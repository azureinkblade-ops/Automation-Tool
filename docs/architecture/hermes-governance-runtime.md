# Hermes Governance Runtime — Store Wiring

## Purpose

This document describes how application/runtime code obtains the authoritative
Hermes governance store after Phase 6. It is the smallest production seam that
wires the governance core into the application **without weakening any Phase 6
boundary**.

## Architecture

```text
application / runtime
        ↓
get_governance_store()              (tools/hermes_core/runtime.py)
        ↓
GovernanceStore (abstract)
        ↓
SQLiteGovernanceStore
        ↓
%LOCALAPPDATA%\Hermes\governance.db
```

Runtime code depends only on `GovernanceStore`, never on `sqlite3.Connection`
or a scattered `SQLiteGovernanceStore(...)` constructor. All construction is
centralized in `get_governance_store()`.

## Production DB location

- Default: `%LOCALAPPDATA%\Hermes\governance.db`
- Override: `HERMES_GOVERNANCE_DB` (absolute path wins)
- Resolution is implemented in `tools/hermes_core/runtime_config.py`:
  `resolve_governance_db_path(env=None)`.
- Resolution has **no filesystem side effect** (no directory/file creation);
  the parent directory is created only when the runtime store is opened.
- Tests use temporary databases exclusively via `set_governance_db_path_override`.
- The governance DB is runtime state and must never be committed.

## State-gate separation

The governance store owns only:

```text
UNDER_REVIEW → CONSENSUS_CALCULATED → ACCEPTED
```

It stops at `ACCEPTED`. It never creates or authorizes
`AWAITING_EXECUTION_AUTHORIZATION`, `AUTHORIZED`, or `EXECUTING`. Those remain
in the broader application lifecycle and require a separate
execution-authorization milestone.

## Connection ownership

Application-lifetime model: `get_governance_store()` constructs the store once
per process and reuses it. `close_governance_store()` releases the connection
and should be called at process shutdown. The store owns its single SQLite
connection; it is not shared across threads.

## Bootstrap behavior

On first construction (inside `SQLiteGovernanceStore.__init__`):

- open SQLite, enable foreign keys
- bootstrap schema v1 (idempotent, version-guarded)
- assert schema version (unsupported newer version fails closed)
- verify persisted-hash re-verification on load

No destructive rebuild, no implicit DB deletion, no silent recovery from
corruption.

## Query surface

Read-only governance questions (no state transition, no authorization, no
worker invocation):

- `get_governance_chain(task_id)`
- `get_governance_state(task_id)` → `"ACCEPTED"` / `"BLOCKED"` / `"ESCALATED"` / `None`
- `verify_governance_integrity()`
- `is_governance_accepted(task_id)`

## Failure policy

A governance-enabled operation whose store is unavailable fails closed
(`GovernanceStoreError`). It never falls back to JSON files, in-memory
acceptance state, `automation_state.db`, Obsidian, or Anytype. No failure path
bypasses execution authorization.

## Execution boundary (invariant)

`ACCEPTED` is governance acceptance ONLY. The runtime seam grants no execution
authorization and invokes no worker. Reading `ACCEPTED` never transitions to
`AUTHORIZED` or `EXECUTING`.

## First real governance consumer

`tools/hermes_core/governance_consumer.py` is the first narrow production-facing
consumer of the governance runtime. It sits between application orchestration
and the runtime provider and answers one question: what is the authoritative
governance status of a task?

```python
from tools.hermes_core import get_task_governance_status

status = get_task_governance_status(task_id)
# status.governance_state: "ACCEPTED" | "CONSENSUS_CALCULATED" | ... | None
# status.accepted: bool
# status.can_authorize_execution: bool  (always False this milestone)
```

- `get_task_governance_status(task_id)` reads through `get_governance_store()`
  and returns a frozen `TaskGovernanceStatus`.
- `can_authorize_execution` is a **hard architectural declaration of `False`**
  (`CAN_AUTHORIZE_EXECUTION` constant), NOT derived from governance state.
  Logic like `can_authorize_execution = (state == "ACCEPTED")` is forbidden.
- Integrity is fail-closed: if the authoritative store is tampered,
  `GovernanceIntegrityError` propagates and is NOT downgraded to
  `accepted = False`.
- No worker launch, no execution authorization, no state transition.

### Integration proof: real review orchestration path

`tools/hermes_core/review_runner.py` (`ReviewRunnerStub.prepare()`) is a real,
non-executing orchestration path that already owns the governance `task_id` and
returns a status object ("Model execution is not authorized in this phase"). As
the Governance Consumer Integration Proof, `prepare()` now enriches its
`ReviewRunnerResult` with the read-only `governance` field by calling the
existing public consumer `get_task_governance_status(task_id)`:

```python
result = ReviewRunnerStub().prepare(session)
# result.governance: TaskGovernanceStatus | None
# result.governance.governance_state: "ACCEPTED" | None | ...
# result.governance.accepted: bool
# result.governance.can_authorize_execution: bool  (always False)
```

This proves deterministic governance truth enters one real application workflow
while remaining observational. The `governance` field is strictly additive
(backward compatible with existing `test_review_runner.py`). Integrity failures
propagate as `GovernanceIntegrityError` (fail-closed), never downgraded to
`accepted = False`. A negative-authority mutation (`can_authorize_execution =
governance.accepted`) breaks the integration test, confirming the boundary.

## Verification

- `tests/hermes_core/test_governance_runtime_config.py` — path resolution,
  override, missing `LOCALAPPDATA`, side-effect-free resolution, rejected
  relative/empty overrides.
- `tests/hermes_core/test_governance_runtime.py` — provider bootstrap/reopen,
  first-consumer query surface, tamper fail-closed, execution-boundary
  regression.
- `tests/hermes_core/test_governance_consumer.py` — unknown task, in-processing
  (non-accepted), accepted (`accepted=True` / `can_authorize_execution=False`),
  tamper fail-closed, no execution side effects.
- `tests/hermes_core/test_review_runner_governance_integration.py` — real
  orchestration path (`ReviewRunnerStub.prepare`) consumes governance status:
  unknown / in-processing / accepted / tamper fail-closed / no worker side
  effects / accepted-true-distinct-from-can-authorize-false.
- Mutation testing: 8/8 runtime mutants each cause >=1 targeted test failure;
  source restored byte-exactly.

## Out of scope

Worker routing, execution authorization, `AUTHORIZED`/`EXECUTING` transitions,
browser automation, social publishing, Anytype/Obsidian machine state. Those
belong to a future execution-authorization milestone.
