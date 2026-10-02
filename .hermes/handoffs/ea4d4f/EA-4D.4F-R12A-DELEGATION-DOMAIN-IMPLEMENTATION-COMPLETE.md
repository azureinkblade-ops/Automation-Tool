# EA-4D.4F-R12A Delegation Domain Implementation Complete

Date: 2026-08-28

## Final State

**EA-4D.4F-R12A IMPLEMENTATION: COMPLETE / NOT COMMITTED**

- R11 design: UNCHANGED / FROZEN.
- R12B: NOT AUTHORIZED.
- R12C-R12E: NOT AUTHORIZED.
- Live Codex or receiver invocation: NOT AUTHORIZED.
- Commit: NOT AUTHORIZED.
- Push: NO.
- GPU / ComfyUI mutation: NOT AUTHORIZED.

R12A implements only the canonical delegation domain and its durable SQLite
store. It does not deliver work to an agent, invoke an agent, or create any
runtime capability for doing so.

## Authority Anchors

- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting HEAD: `67872e9d19d28294c9b8f8dc8ae28d3bec9ba5a3`
- Starting parent: `0fc8766f6ac879edb2161bd123752c68b7e4aa0d`
- Frozen R11 design SHA-256:
  `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- Governing authorization:
  `EA-4D.4F-R12A IMPLEMENTATION AUTHORIZATION - Canonical Delegation Domain + Durable SQLite Store`

## Files Changed

Production surface, exactly two new modules:

1. `tools/hermes_core/delegated_task.py`
2. `tools/hermes_core/sqlite_delegation_store.py`

Focused test surface, exactly two new files:

1. `tests/hermes_core/test_delegated_task.py`
2. `tests/hermes_core/test_sqlite_delegation_store.py`

Governance records:

1. `.hermes/handoffs/ea4d4f/EA-4D.4F-R12A-DELEGATION-DOMAIN-IMPLEMENTATION-COMPLETE.md`
2. `.hermes/handoffs/ea4d4f/EA-4D.4F-IMPLEMENTATION-CONTINUATION.md`
3. `C:\Users\David\Documents\Hermes Vault\Hermes\EA-4D.4F Implementation Continuation.md`

No EA-4D.4A-E production semantics were changed.

## Canonical Domain Contract

`delegated_task.py` provides immutable canonical representations for delegated
tasks and least-authority capability leases. It includes:

- strict normalization of identifiers, text, timestamps, and structured input;
- deterministic `task_input_hash` computation;
- deterministic `delegation_id` computation in its own identity domain;
- immutable dataclass construction and canonical serialization;
- reconstruction with integrity verification;
- least-authority capability validation;
- fail-closed rejection of malformed, ambiguous, or non-canonical data.

Capability validation materializes requested tools once before comparison. This
prevents a generator or one-shot iterable from being consumed during one check
and then bypassing a later check.

## Durable SQLite Contract

`sqlite_delegation_store.py` implements schema version **1** with these tables:

- `delegation_schema_version`
- `delegations`
- `capability_leases`
- `delegation_cancellations`
- `lease_revocations`

The store uses `BEGIN IMMEDIATE` for mutation transactions and explicitly closes
every SQLite connection. Fresh databases initialize schema version 1. Reopening
a current schema does not mutate it. A database declaring an unsupported schema
version fails closed.

### Replay And Conflict Semantics

- Creating a delegation with the same canonical identity and identical payload
  is an exact replay and returns the durable existing record.
- Reusing a delegation identity with divergent canonical content is a conflict
  and fails closed.
- Issuing the same canonical lease is replay-safe and idempotent.
- Divergent lease replay, or conflicting attempt/route linkage, fails closed.
- Integrity reads reconstruct canonical domain objects and verify their hashes
  and physical linkage columns rather than trusting stored JSON alone.

### Cancellation And Revocation Persistence

- Delegation cancellation and lease revocation are durable events in separate
  tables.
- Exact event replay is idempotent.
- Reusing an event identity with divergent content is a conflict.
- A cancelled delegation cannot become deliverable.
- A revoked or expired capability lease cannot authorize delivery.
- Cancellation and revocation remain visible after store reopen.

## Defects Found And Corrected

### Windows SQLite Connection Lifecycle

Initial focused tests exposed SQLite connections that remained open long enough
to prevent temporary database cleanup on Windows. This was a real portability
defect in the new R12A store.

Fix: every production and direct test SQLite connection is now managed with
`contextlib.closing`, while transaction commit/rollback remains explicit. The
focused suite and complete Hermes Core suite subsequently completed without
leaked-handle cleanup failures.

### Tamper-Test Fixture Persistence

Four integrity/schema tamper tests modified SQLite rows but did not commit their
deliberate corruption before the connection closed. The production integrity
checks were therefore receiving unchanged fixtures.

Fix: the four tests now commit their deliberate corruption before invoking the
production reader. This is a fixture correction; it does not weaken or alter the
production contract.

## Identity Separation

Focused tests explicitly prove that all currently known identities remain in
separate domains:

- `delegation_id`
- `task_input_hash`
- `capability_lease_id`
- `ExecutionAuthorization` ID
- `ExecutionAttempt` ID
- `ExecutionLaunchAttempt` ID
- runtime identity
- future receiver-acceptance identity
- future result identity

No one of these values is substituted for or inferred to be another.

## Negative Capability Verification

The two new production modules were inspected and tested to confirm they contain
no runtime capability for:

- subprocess or shell launch;
- network access;
- Codex invocation;
- Kilo invocation;
- browser automation;
- MCP;
- GPU or ComfyUI;
- scheduling;
- Studio Bible or image-pipeline work;
- Regional Hand Repair.

Their imports are limited to Python data/SQLite utilities and existing Hermes
hashing/domain helpers. Regional Hand Repair remains qualification evidence only
and is not a dependency of this implementation.

## Verification Evidence

Runtime interpreter used for every command:

`C:\Users\David\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

All pytest commands used `-q -p no:cacheprovider --tb=line` and an isolated
`--basetemp` below `.pytest-r12a-tmp`.

| Gate | Scope | Current result |
| --- | --- | --- |
| R12A focused | `test_delegated_task.py`, `test_sqlite_delegation_store.py` | **50 passed, 15 subtests passed** in 0.62s |
| EA-4D.4E | dispatcher acceptance/recovery | **19 passed** in 0.41s |
| EA-4D.4D | post-launch orchestrator acceptance/recovery | **11 passed** in 0.42s |
| EA-4D.4C | state projection orchestrator/policy | **11 passed** in 0.26s |
| EA-4D.4B | state projector/persistence/recovery | **25 passed** in 0.77s |
| EA-4D.4A | start result service/persistence/recovery | **28 passed** in 0.55s |
| Authority / attempt stores | authorization, issuance, claim, attempts, concurrency | **303 passed** in 38.06s |
| Worker routing | worker router focused suites | **85 passed** in 9.83s |
| Launch admission / coordinator | admission, coordinator, recovery, real probe | **33 passed** in 1.66s |
| Start result | start domain, concurrency, result/persistence/recovery | **116 passed** in 2.56s |
| Start-store migration | execution start store migration | **11 passed** in 0.27s |
| Complete Hermes Core | `tests/hermes_core/` | **1,071 passed, 47 subtests passed** in 89.67s |

`py_compile` also completed cleanly for all four new source/test files.

## Regression Classification

- New R12A regressions: **0**.
- Remaining focused failures: **0**.
- Remaining complete Hermes Core failures: **0**.
- The Windows connection lifecycle failure was an R12A implementation defect and
  was fixed within the authorized two-module surface.
- The four tamper failures were test-fixture defects and were corrected without
  changing production semantics.
- No broad-suite failure required a change to EA-4D.4A-E.

## Stop Boundary

R12A has built the durable delegation substrate only. It has not implemented
receiver delivery, receiver acceptance, agent invocation, result return, or a
live handoff.

**EA-4D.4F-R12A IMPLEMENTATION: COMPLETE / NOT COMMITTED**

**R12B: NOT AUTHORIZED**

**R12C-R12E: NOT AUTHORIZED**

**COMMIT: NOT AUTHORIZED**

**PUSH: NO**
