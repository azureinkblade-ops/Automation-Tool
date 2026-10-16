# EA-4E.92KP network-grant store v4 design

Status: NON-LIVE DESIGN CANDIDATE / NOT IMPLEMENTED OR AUTHORIZED.
Parent: `158b4eda820679f7928360cba8a245b8fd403eb0`.

## Observed gap

The current `Ea4eDockerMutationStoreIdentity` v3 journal/anchor checks
cover its `mutation_fake_grants` row digest only. The 92KO v2 candidate
adds issuer, ceremony, authority, label, command-spec, and artifact-byte
bindings that v3 neither stores nor hashes. Adding a separate table without
including it in every generation's digest would permit undetected changes
to those candidate bytes. The v3 store is fake-qualified, not a protected
issuer store, and it must not silently migrate or become real authority.

## Proposed v4 boundary

1. Use a distinct store schema ID and a fresh store ID/epoch. Do not open a
   v3 store as v4 or import its fake grants as issued authority. Keep v3
   tests and evidence reproducible.
2. Persist exact canonical v2 artifact bytes (ASCII text), their SHA-256,
   one current state, and a unique grant/nonce/attempt-action/target-name
   identity. The protected writer must revalidate the bytes against the
   independent ceremony expectations at issue time. The source worktree
   cannot supply its own trusted expectations.
3. Include every persisted artifact byte and mutable state field in a
   deterministic row digest, then bind that digest to every journal
   generation and external anchor. Reject extra rows, duplicates, missing
   anchors, changed store identity/epoch, and altered artifact bytes on
   every reopen and before every transition.
4. Issue, claim, revoke, and terminal uncertain-outcome transitions each
   use one `BEGIN IMMEDIATE` transaction with exact prior-state predicates.
   A claim consumes the one-attempt budget before Docker mutation. Reopen
   or replay cannot replenish it; `CLAIMED`/`IN_FLIGHT` never auto-retry.
5. A crash after database commit but before the matching anchor is written
   must deny reopening and all further issue/claim activity. Recovery is a
   separately reviewed, read-only reconciliation decision, not an implicit
   anchor rebuild or a retry. An implementation must prove the exact crash
   windows with injection tests before any real issuance.
6. Current cancellation/revocation and expiry are read from the v4 store at
   claim time. The immutable v2 `state_at_issue` field does not prove
   current state. The trusted clock, operator UAC witness, current authority
   identity, protected binary, installation ACL/reparse closure, and exact
   Docker endpoint/executable remain independent gates.

## Required fake-only qualification

Cover v3/v4 cross-open denial; canonical-byte/hash tamper; issuer, ceremony,
authority, request, label, target, store ID/epoch and source drift; duplicate
grant/nonce/attempt-action/target; concurrent issue/claim; expiry,
cancellation and revocation before claim; replay after claim; missing or
foreign anchor; database/anchor rollback; crash before commit, after commit
before anchor, and after anchor; and reopen from a fresh process. Tests must
prove no Docker, receiver, model, GPU, or ComfyUI capability is imported.

This is a design candidate, not a frozen contract roll or implementation.
It grants no UAC, real issuance, Docker mutation, receiver/model execution,
or production activation. Production remains HOLD.
