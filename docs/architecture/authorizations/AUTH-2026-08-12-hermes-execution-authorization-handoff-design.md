---
title: "AUTH-2026-08-12 Hermes Execution Authorization Handoff Design"
document_id: "AUTH-2026-08-12-HERMES-EXECUTION-AUTHORIZATION-HANDOFF-DESIGN"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
---

# AUTH-2026-08-12 Hermes Execution Authorization Handoff Design

This authorization permits **DESIGN ONLY** of the future boundary that takes a
governance-accepted task and, through a separate explicit authority mechanism,
makes it eligible for execution. It extends `ADR-0004` (acceptance vs execution)
and the consumer milestones (`209492c`, `291b68b`).

## Authorized scope (design deliverables only)

1. `docs/architecture/hermes-execution-authorization-handoff.md` — primary design
   (26-section structure: purpose, boundary, threat model, authority model,
   domain separation, `ExecutionAuthorization` artifact, request/decision model,
   state machine, persistence, store interfaces, ledger/integrity, replay,
   concurrency/claims, expiry, revocation, worker handoff, crash recovery,
   attempts, retries, input binding, operator UX, failure semantics, test
   strategy, implementation phases, unresolved questions, recommendation).
2. `docs/architecture/decisions/ADR-0013-execution-authority-separate-from-governance.md`
   — authority/persistence separation decision.
3. Architecture index/README update.

## Explicit non-scope (prohibited in this milestone)

- No production `ExecutionAuthorization` issuance.
- No execution-state mutation (`AUTHORIZED`, `EXECUTING`,
  `AWAITING_EXECUTION_AUTHORIZATION`).
- No worker launch, routing, enqueue, or execution dispatch.
- No `ExecutionAuthorizationStore` / `ExecutionClaim` / `WorkerRouter`
  implementation.
- No `app.py` change; `automation_state.db` remains unrelated.
- No execution authority or worker behavior introduced.

## Key design decisions (for the record)

- Authority owner: distinct `Execution Authority` domain (HYBRID human+policy);
  governance engine never grants authority.
- Persistence: **separate `execution_authority.db`** (Option B), not governance.db.
- Store interface: new `ExecutionAuthorizationStore`, not `GovernanceStore`.
- `ExecutionAuthorization` binds by hash to immutable `AcceptanceArtifact`.
- Atomic `ExecutionClaim` required (at-most-one-claim).
- Fail-closed `ExecutionAuthorizationIntegrityError` (distinct from
  `GovernanceIntegrityError`).
- `ACCEPTED` never grants `AUTHORIZED`/`EXECUTING` without valid authorization.

## Verification

- Documentation-only milestone; no production Python changed.
- `git diff --check` clean for any touched doc files.
- Full Hermes core baseline remains 284/284 PASS (unchanged; no code change).
- Unrelated dirty/untracked work preserved, not staged.
