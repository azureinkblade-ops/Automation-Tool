# ADR-0013 Execution Authority Is Separate From Governance Acceptance

* **Status:** PROPOSED (design milestone `ARCH-EXEC-AUTH-HANDOFF`, 2026-08-12)
* **Date:** 2026-08-12
* **Decision owners:** David Powell
* **Scope:** Execution authorization authority & persistence
* **Related:** ADR-0004 (acceptance vs execution, ACCEPTED), ARCH-EXECUTION
  (execution-model.md), hermes-governance-store.md, hermes-acceptance-artifact.md

## Context

Phase 6 established deterministic governance whose ownership ends at `ACCEPTED`.
The First Real Governance Consumer and its Integration Proof confirmed
`can_authorize_execution` is hard-declared `False` and that `ReviewRunnerStub`
observes governance truth without gaining authority. ADR-0004 already mandated
that acceptance and execution authorization be separate artifacts/transitions,
but did not specify the *authority owner, persistence boundary, store
interface, ledger, replay, expiry, revocation, or claim* design. This ADR records
that concrete decision before any implementation begins.

The repository already contains an execution envelope
(`docs/architecture/execution-model.md`) carrying `authorization_sha256` +
`parent_acceptance_sha256`, but nothing yet *issues* that authorization hash.
This ADR defines the issuing authority.

## Decision

1. **Separate authority domain.** Execution authorization is owned by a distinct
   `Execution Authority` domain, not by the governance engine. The governance
   components (`ConsensusEvaluator`, `TerminalConsensusDisposition`,
   `AcceptanceArtifact`, `GovernanceStore`, `get_task_governance_status()`,
   `ReviewRunnerStub.prepare()`) may supply evidence but never become the
   authorization principal.

2. **Separate persistence (Option B).** Execution-authorization truth lives in a
   dedicated database, `%LOCALAPPDATA%\Hermes\execution_authority.db`, NOT in the
   governance `governance.db`. This prevents `GovernanceStore` from silently
   acquiring authority it explicitly does not own. Cross-store linkage is by hash
   reference (`accepted_governance_hash`), never by shared transaction.

3. **Separate store interface.** A new `ExecutionAuthorizationStore` (with
   `record_/get_/consume_/revoke_execution_authorization`) is introduced;
   `GovernanceStore` is NOT extended with execution-authority methods.

4. **Immutable `ExecutionAuthorization` artifact** binds by hash to the immutable
   `AcceptanceArtifact` (`acceptance_id` / `acceptance_sha256`). Bare `task_id`
   binding is insufficient and rejected.

5. **Atomic `ExecutionClaim`** sits between authorization and execution, giving
   at-most-one-claim semantics and an audit event before any worker runs.

6. **Fail-closed integrity.** A new `ExecutionAuthorizationIntegrityError`
   (distinct from `GovernanceIntegrityError`) is raised on tampering; it is not
   downgraded to an ordinary "not authorized" miss.

7. **No automatic authority from acceptance.** `ACCEPTED` never transitions to
   `AUTHORIZED_FOR_EXECUTION` or `EXECUTING` without a valid
   `ExecutionAuthorization` + matching acceptance hash + not-expired/revoked/
   consumed + scope match.

## Consequences

### Positive
* Governance acceptance cannot accidentally trigger execution.
* Authority ownership is unambiguous and auditable.
* Cross-store hash binding prevents acceptance-substitution and input mutation.
* Single-use/atomic claims + separate DB contain replay and boundary erosion.

### Negative
* An additional domain, database, store interface, and ledger to build/maintain.
* Operators must understand three distinct layers (governance / authority /
  runtime).
* Cross-store reconciliation is by reference, not transaction.

## State flow (extends ADR-0004)

```text
ACCEPTED                         (Governance owns)
  → AWAITING_EXECUTION_AUTHORIZATION
  → AUTHORIZED_FOR_EXECUTION
  → EXECUTION_CLAIMED            (new atomic-claim state)
  → EXECUTING                    (Execution Runtime owns)
  → EXECUTION_VERIFIED
```

## Implementation gate

EA-3 (authorization decision/issuance service) is the first phase introducing
real execution-capability issuance and requires a separate, explicit user
authorization before implementation.
