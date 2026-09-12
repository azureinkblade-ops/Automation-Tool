# EA-4E.67H Anchor Publication Coordination

Deterministic race reproduction: two failures before production correction,
for same-instance and independently reopened-store claimers. Both observed
database/anchor generation mismatch while the first writer was paused at the
post-commit/pre-anchor seam. This confirms the publication gap, not an unsafe
double permit; at-most-one consumption remains required.

## Correction and Design

Every store-owned _connection operation holds BEGIN IMMEDIATE on a sibling
`<authorization-database-name>.coordination.sqlite3` until its main database
connection is closed and anchor publication has completed or failed.
The coordination transaction is never committed and contains no authority or
authorization data. Closing its connection releases SQLite's advisory lock.
Independent store instances share its canonical path; SQLite provides the
cross-process locking primitive, but no multiprocess qualification was executed
in this strict process-free slice.

Acquisition is bounded by the existing 1000ms busy timeout. Missing/unwritable,
corrupt, or locked coordination state fails closed; there is no unsynchronized
fallback. The coordination path cannot alias the configured external anchor;
initialization checks this before creating either authoritative file.

Existing DB and anchor schema versions remain 1. Their material, identity,
generation advancement, record hashes, and rollback/crash semantics are unchanged.
No claim is automatically restored or reissued. An interrupted publication still
leaves an integrity mismatch that fails closed after coordination is released.
External trust assumptions about jointly rolled-back database/anchor are unchanged.

The new sidecar is runtime coordination infrastructure, not a new durable source
of truth. Provisioning/reopening an existing store creates it as needed. Read-only
deployments must permit its creation or will fail closed. Concurrent first-ever
initialization is not newly qualified; explicit initialization semantics remain.
Raw private _connect callers bypass coordination and are not supported owners.

## Candidate Verification

- Race/lock tests plus complete invocation suite: 43 passed / 0 failed / 0 events.
- Complete 11-file predecessor ladder: 360 passed / 0 failed / 0 events.
- Restart/rollback/tamper/crash subset: 82 passed / 3 deselected / 0 events.
  Two exact old-ID tests await successor reseal; one real multiprocess test is
  deliberately outside the process-free subset, not counted as a pass.

These gates ran against isolated successor WIP. Checkpoint only:
tools/hermes_core/durable_invocation_authorization_store.py,
tests/hermes_core/test_ea4e67h_anchor_publication_concurrency.py,
and this evidence. Successor source/test WIP is excluded.

Required post-commit gate on clean export: complete 32 restart and 33A rollback
suites plus five new race/lock tests, excluding ONLY the real multiprocess test.
The committed baseline still pins 7.5.16, so old exact-ID tests must pass unchanged
in that export. No source-promotion or full-Hermes-green claim is made.

No receiver/model task, authorization issuance, durable live-store mutation,
binding renewal, GPU/ComfyUI work, live checkout edits, or deployment.
