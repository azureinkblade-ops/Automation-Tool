---
title: "ADR-0014 Execution Authorization Issuance Requires Explicit Authority Decision"
status: accepted
date: 2026-08-13
decision-makers: Hermes Agent (David)
consulted:
  - docs/architecture/hermes-execution-authorization-handoff.md
  - docs/architecture/decisions/ADR-0013-execution-authority-separate-from-governance.md
  - docs/architecture/decisions/ADR-0004-acceptance-vs-execution.md
  - docs/architecture/hermes-execution-authorization-issuance.md
---

# ADR-0014 — Execution Authorization Issuance Requires Explicit Authority Decision

## Context

EA-1 delivered immutable execution-authorization domain artifacts. EA-2 delivered
durable, integrity-verified persistence in a separate `execution_authority.db`.
Neither introduces real authority: no issuance, no claim, no worker, no execution
transition. EA-3 is the first phase that can create a real `ExecutionAuthorization`.

Before any callable issuance component exists, the trust boundary and issuance
contract must be frozen. Key findings from EA-3D inspection:

- The current `ExecutionAuthorization` binds to `AcceptanceArtifact`
  (`accepted_governance_artifact_id` + `accepted_governance_hash`) but does NOT
  carry `request_id`/`request_hash` or `decision_id`/`decision_hash`. The
  Authorization-to-Decision link is currently one-way (via
  `ExecutionAuthorizationDecision.authorization_id` only).
- EA-2 exposes separate `record_decision` + `record_authorization` calls, which
  cannot guarantee atomic grant issuance.
- `worker_class = None` and `expires_at = None` have ambiguous issuance semantics.

## Decision

1. **Issuance requires an explicit authority decision.** A real
   `ExecutionAuthorization` is created only by an issuance service that has (a)
   validated the governance acceptance binding, (b) validated request integrity,
   (c) validated actor identity + authority role, (d) resolved and evaluated
   policy, and (e) produced a `GRANTED` `ExecutionAuthorizationDecision`. No
   shortcut from acceptance or request directly to authorization.
2. **HYBRID authority, explicit matrix.** `HUMAN` and `POLICY_SERVICE` may
   decide/issue within bounded scopes; `POLICY_SERVICE` may auto-issue ONLY
   explicitly enumerated low-risk scopes (default NONE); `SYSTEM` may never grant.
3. **Request prerequisite.** Every issuance begins from a persisted
   `ExecutionAuthorizationRequest`; every authorization is preceded by a
   `GRANTED` decision.
4. **Atomic grant.** `GRANTED` decision + `ExecutionAuthorization` are persisted
   in one transaction (dedicated EA-2 store method). Denial persists only the
   `DENIED` decision.
5. **Domain amendment required.** `ExecutionAuthorization` gains
   `request_id`/`request_hash`/`decision_id`/`decision_hash` (and
   `ExecutionAuthorizationDecision` gains `request_hash`) so the chain
   Authorization to Decision to Request to Acceptance is cryptographically bound.
6. **Fail-closed.** Any uncertainty about identity, acceptance, policy, scope,
   time, integrity, or persistence yields NO authorization.
7. **No worker/claim/execution behavior.** Issuance persists representations only;
   it never claims, launches, or transitions execution runtime.
8. **AUTHORIZED_FOR_EXECUTION is a derived condition**, not first-class mutable
   state, to avoid state drift.
9. **Null expiry prohibited** in initial EA-3; `expires_at` is bounded and
   absolute UTC.
10. **Idempotency.** One terminal decision per `request_id`; at most one
    authorization per request.

## Status

Accepted as design (EA-3D). Implementation (EA-3I) requires separate explicit
authorization and completion of the domain + store amendments.

## Consequences

- Positive: trust boundary is explicit and auditable; substitution threats are
  closed by cryptographic bindings; issuance is fail-closed and atomic.
- Negative: EA-3I cannot start until the EA-1 domain amendment and EA-2 store
  amendment land with tests. This is intentional gating, not delay.
- `ACCEPTED != EXECUTION AUTHORIZATION` is preserved end-to-end.
