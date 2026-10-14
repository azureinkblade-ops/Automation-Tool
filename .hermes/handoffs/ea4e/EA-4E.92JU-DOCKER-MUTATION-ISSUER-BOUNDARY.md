# EA-4E.92JU Docker mutation issuer boundary

Status: NON-LIVE DESIGN / NO ISSUER IMPLEMENTED.
Governing source: `8092ee2bd27f567f84137f1805f1ad2ebd1420ff`.

## Decision

EA-4E.92JT requires four independent mutation budgets: `network_create`,
`gateway_create`, `gateway_start`, and `kilo_container_create`. The existing
production invocation and activation authorization artifacts are not Docker
mutation grants and must not be reinterpreted as such. The v2 92JO request
remains an input candidate for the last action only, with all authority flags
false. Its reported network/gateway IDs cannot bootstrap their own ownership.

The accepted local-Docker profile trusts local administrators and Docker, not
arbitrary application callers. Issuance must be a separate operator ceremony
outside the app request/receiver path, backed by a distinct durable mutation
authorization store and audit journal. An injected `verified=True`, caller
supplied authorization ID, SQLite row hash, Docker label, or matching inspect
is not an operator/issuer witness.

## Artifact and store contract

One immutable artifact binds: schema/version, action enum, authorization ID,
issuer identity, store installation ID/epoch, governing commit, delegated
attempt and current authority identity, operator witness identity, exact
Docker endpoint and executable digest, target deterministic name/labels,
predecessor claim hashes, requested command/spec hash, nonce, issue/expiry
times, cancellation/revocation state, and one-attempt budget. The gateway
actions also bind the pinned fake-gateway image index/manifest, network ID,
alias, and effective no-port/no-mount policy. The Kilo create artifact binds
the 92JO v2 request hash, reserved plan, pinned receiver image, prepared
mount-source digests, network owner and gateway owner claim hashes, and
`start_authorized=false`. No artifact for one action grants another action.

The store must reject duplicate nonce, attempt/action collision, source or
store-lineage drift, stale/revoked/expired authority, and conflicting reissue
under a single `BEGIN IMMEDIATE` transaction. Reopen and exact replay may
report the same issued artifact but may not replenish a consumed budget.
Issuance and consumption events are append-only; crash/uncertain outcome
enters a non-retryable state pending read-only reconciliation. Store digests
are local integrity checks, not administrator-resistant signatures under the
accepted threat model.

## Implementation and qualification gates

1. Bind a concrete operator witness and independent ceremony entry to the
   accepted local-Docker profile. Do not turn application request arguments
   into `operator_verified` or call the existing activation ceremony.
2. Implement the separate store/issuer and action-specific verifier, with
   isolated SQLite fake tests for duplicate issue, concurrent issue, replay,
   expiry/revocation, epoch/rollback drift, wrong action, wrong predecessor,
   and crash before/after claim. Keep the issuer free of Docker/process/model
   capabilities.
3. Implement durable owner claims and the process-tree-contained mutation
   driver only after the issuer contract is qualified. Each mutation needs
   its own narrow real authorization; broad continuation approval does not
   become a reusable Docker mutation budget.
4. Qualify observed network/gateway ownership before asking for Kilo create.
   Kilo start, provider/model use, and production activation remain separate.

This packet implements no issuer, owner, Docker mutation, receiver execution,
or production activation. Production remains HOLD.
