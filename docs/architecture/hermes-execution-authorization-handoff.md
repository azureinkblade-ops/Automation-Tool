---
title: "Hermes Execution Authorization Handoff Design"
document_id: "ARCH-EXEC-AUTH-HANDOFF"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
related:
  - ADR-0004-acceptance-vs-execution
  - ARCH-EXECUTION (execution-model.md)
  - hermes-governance-store.md
  - hermes-governance-runtime.md
  - hermes-acceptance-artifact.md
---

# Hermes Execution Authorization Handoff Design

This is a **DESIGN-ONLY** milestone. It defines the future boundary that can take a
governance-accepted task and, through a separate explicit authority mechanism,
make it eligible for execution. **No production code is implemented here.** The
invariant established across Phase 6 and the consumer milestones is preserved:

```text
ACCEPTED != EXECUTION AUTHORIZATION
```

## 1. Purpose

Design the authority layer that sits between:

```text
deterministic evidence → review → consensus → disposition
    → acceptance artifact → persisted governance truth → ACCEPTED
```

and the future:

```text
ACCEPTED → explicit execution-authorization authority
    → authorization artifact → AUTHORIZED → worker routing
```

Governance acceptance is *necessary evidence* for authorization where policy
requires it, but is **never itself the thing that grants authority**. The
forbidden model `authorized = governance_status.accepted` must not exist.

This design extends **ADR-0004** (ACCEPTED), which already mandated the
separation and a state flow (`ACCEPTED → AWAITING_EXECUTION_AUTHORIZATION →
AUTHORIZED_FOR_EXECUTION → EXECUTING → EXECUTION_VERIFIED`). ADR-011 (this
milestone's ADR) records the concrete authority/persistence decision. The
existing `docs/architecture/execution-model.md` (ARCH-EXECUTION) already defines
the *execution envelope* that consumes an `authorization_sha256` +
`parent_acceptance_sha256`; this document designs the authority that *issues*
that authorization hash.

## 2. Existing boundary

- Governance owns `UNDER_REVIEW → CONSENSUS_CALCULATED → ACCEPTED` only
  (`_ALLOWED_GOVERNANCE_TRANSITIONS` in `sqlite_governance_store.py`).
- `get_task_governance_status(task_id)` returns observational status with
  `can_authorize_execution` hard-declared `False`.
- `AcceptanceArtifact` (`acceptance_artifact.py`) is immutable, with
  `acceptance_id` (`acceptance-{sha256[:16]}`) and `acceptance_sha256`.
- No production execution, worker, or `AUTHORIZED`/`EXECUTING` state exists.

## 3. Non-goals

- No worker launch, routing, enqueue, or execution dispatch.
- No production `ExecutionAuthorization` issuance, persistence, or consumption.
- No `AUTHORIZED`/`EXECUTING`/`AWAITING_EXECUTION_AUTHORIZATION` transition in
  this milestone.
- No change to `app.py`, `automation_state.db`, or the governance store's
  responsibility.

## 4. Threat model

| # | Threat | Required outcome |
|---|--------|-----------------|
| 1 | Governance bypass (no ACCEPTED) requests authorization | DENY where policy requires acceptance |
| 2 | Acceptance substitution (auth references different task/input) | integrity/validation failure |
| 3 | Replay of consumed single-use authorization | DENY |
| 4 | Expired authorization used | DENY |
| 5 | Revoked authorization used | DENY |
| 6 | Unauthorized actor grants authorization | DENY + audit event |
| 7 | Scope escalation (auth A, request B) | DENY |
| 8 | Input mutation (bound hash X, present Y) | DENY |
| 9 | Concurrent claims on one-use authorization | exactly one succeeds |
| 10 | Manual tampering of persisted auth/claim | explicit integrity failure (not ordinary denial) |

## 5. Authority model

- **Owner:** a distinct `ExecutionAuthority` domain, NOT the governance engine.
  Forbidden owners: `ConsensusEvaluator`, `TerminalConsensusDisposition`,
  `AcceptanceArtifact` builder, `GovernanceStore`, `get_task_governance_status()`,
  `ReviewRunnerStub.prepare()`. These may supply *evidence* but never become the
  authorization principal.
- **Model:** **HYBRID** — system issues authorization only after an explicit,
  authenticated actor decision. The recommended default is **human-operator
  authorization for high-impact operations**, with a policy service eligible for
  low-risk, scope-bounded, pre-approved operation classes. The actor type is
  recorded explicitly (`actor_type: human | service | policy`).
- **Why hybrid:** preserves human control for dangerous actions (ADR-0004
  positive consequence) while allowing automation for bounded, low-risk scopes.

## 6. Domain separation

```text
Governance domain        owns: UNDER_REVIEW, CONSENSUS_CALCULATED, ACCEPTED
Execution Authority domain owns: authorization requests, decisions,
                                  ExecutionAuthorization, expiry/revocation,
                                  execution claims
Execution Runtime domain  owns: worker routing, EXECUTING, execution result
```

Dependency direction (upward only):

```text
Execution Runtime ↑ Execution Authority ↑ Governance
```

Governance must not depend on execution authority or workers.

## 7. ExecutionAuthorization artifact

Immutable artifact issued by `ExecutionAuthority`. Binds to governance evidence
by hash. Required fields:

```yaml
authorization_id: "execauth-{sha256[:16]}"   # deterministic from core doc
task_id: "<task>"
accepted_governance_artifact_id: "<acceptance-{sha256[:16]}>"
accepted_governance_hash: "<acceptance_sha256>"   # binds immutable acceptance
authorization_actor: "<actor_id>"
authorization_actor_type: "human | service | policy"
authorized_scope:
  operation: "<exact operation key>"           # e.g. stage2-v1-gpu-execution
  worker_class: "<worker id>"
  input_hash: "<hash of authorized inputs>"     # input-mutation protection
  environment: "<target>"
  attempt_limit: 1 | N                          # single-use vs bounded-retry
  max_runtime_seconds: <int>
  resource_ceiling: {...}
authorization_reason: "<text>"
authorization_policy_id: "<id>"
authorization_policy_version: "<version>"
issued_at: "<iso8601>"
expires_at: "<iso8601 | null>"                # null = no expiry (rare; policy-gated)
nonce: "<replay-control identifier>"
artifact_version: "1.0"
artifact_hash: "<sha256 of canonical doc excluding artifact_hash>"
```

Decided NOT required (kept optional / out of v1):
- `authorized_worker_class` is folded into `authorized_scope.worker_class`;
- `parent authorization` / `revocation reference` handled by the ledger, not the
  artifact body (immutable artifact stays pure);
- `authorized_input_hash` is required (input-mutation protection), not optional.

The artifact hash (`artifact_hash`) is what the execution envelope's
`authorization_sha256` (ARCH-EXECUTION §2) will carry — closing the existing
binding gap.

## 8. Authorization request / decision model

Recommended: **conditional `ExecutionAuthorizationRequest`** before issuance for
human/policy review paths. Flow:

```text
ACCEPTED → ExecutionAuthorizationRequest(scope, reason, policy)
    → explicit decision (human approval queue / policy service)
    → ExecutionAuthorization (GRANTED) | ExecutionAuthorizationDecision (DENIED)
```

Denial is a first-class `ExecutionAuthorizationDecision` with
`outcome: GRANTED | DENIED` and `denial_reason`. **Denial never alters governance
acceptance** — `governance = ACCEPTED` and `authorization = DENIED` can coexist.
System-only low-risk scopes MAY skip the request artifact and issue directly,
logged as a `GRANTED` decision event.

## 9. State machine

Smallest state machine (execution-authority domain owns all post-ACCEPTED
states):

```text
ACCEPTED                       (governance owns)
  → AWAITING_EXECUTION_AUTHORIZATION
  → AUTHORIZED_FOR_EXECUTION
  → EXECUTION_CLAIMED
  → EXECUTING                    (execution runtime owns)
  → EXECUTION_SUCCEEDED
```

Failure/revocation (append-only, never mutate):

```text
AUTHORIZATION_EXPIRED
AUTHORIZATION_REVOKED
EXECUTION_FAILED
EXECUTION_CANCELLED
```

Names follow ADR-0004's `AUTHORIZED_FOR_EXECUTION` / `EXECUTING` /
`EXECUTION_VERIFIED` vocabulary; `EXECUTION_CLAIMED` is the new atomic-claim
state (§16). Governance ownership ends at `ACCEPTED`; every later state is a
distinct execution/application-authority layer.

**Critical transition invariant:** no direct `ACCEPTED → EXECUTING` or
`ACCEPTED → AUTHORIZED_FOR_EXECUTION`. Required precondition:

```text
VALID ExecutionAuthorization
AND matching accepted_governance_hash
AND not expired / not revoked / not consumed
AND scope matches requested operation
→ AUTHORIZED_FOR_EXECUTION
```

## 10. Persistence architecture

**Option B — separate execution-authority database**, recommended:

```text
%LOCALAPPDATA%\Hermes\execution_authority.db
```

Rationale: stronger domain/authority separation; `GovernanceStore` cannot
accidentally become an authorization store; prevents the boundary erosion risk
identified in inspection. Cross-store linkage is by **hash reference**
(`accepted_governance_hash`), not by transaction — matching ADR-0004's separate
artifacts principle. Option A (same DB) is rejected for v1 because it would
weaken the explicit "governance owns only ACCEPTED" guarantee.

`automation_state.db` remains unrelated; it is NOT repurposed as authorization
truth.

## 11. Store interfaces

Do **NOT** extend `GovernanceStore`. Introduce a new interface:

```python
class ExecutionAuthorizationStore:
    record_execution_authorization(artifact) -> None
    get_execution_authorization(auth_id) -> ExecutionAuthorization
    consume_execution_authorization(auth_id, claim_id) -> None   # atomic, single-use
    revoke_execution_authorization(auth_id, actor, reason) -> None
```

Mirrors `GovernanceStore`'s frozen-dataclass + `ValueError`-subclass-error
conventions (`ExecutionAuthorizationError(RuntimeError)`,
`ExecutionAuthorizationIntegrityError`, `ExecutionAuthorizationConflictError`).
Separate interface keeps authority ownership unambiguous.

## 12. Ledger and integrity

A dedicated hash-linked ledger (`ExecutionAuthorityLedger`, reusing
`tools/hermes_core/ledger.py`'s `Ledger` model) records authorization events:

```text
AUTHORIZATION_REQUESTED, AUTHORIZATION_GRANTED, AUTHORIZATION_DENIED,
AUTHORIZATION_REVOKED, AUTHORIZATION_EXPIRED, AUTHORIZATION_CONSUMED,
EXECUTION_CLAIMED, EXECUTION_STARTED, EXECUTION_COMPLETED, EXECUTION_FAILED
```

Each entry: `payload_sha256`, `previous_entry_sha256`, `entry_sha256`, actor
identity, timestamp (monotonic local clock; see §13), artifact hash. Replay
handling: ledger is append-only; a `CONSUMED` entry for a single-use auth makes
any later `CLAIM` fail closed.

## 13. Replay / idempotency

- **Single-use default:** `attempt_limit = 1`. `consume_execution_authorization`
  atomically marks `CONSUMED` (or decrements a bounded counter).
- Replay of a consumed auth → ledger shows `CONSUMED` → DENY (fail-closed).
- `nonce` + `authorization_id` make duplicate issuances idempotent by operation
  key; renewal requires a new request.
- Bounded-retry (`attempt_limit = N`) permits N claims, each a distinct
  `EXECUTION_CLAIMED` event; the N+1st fails.

## 14. Concurrency / atomic claims

Two callers claim the same one-use authorization concurrently:

- `consume_execution_authorization` runs inside a SQLite transaction with a
  `SELECT ... FOR UPDATE`-style guarded read (or `BEGIN IMMEDIATE`) on the auth
  row.
- The first commit writes `CONSUMED` + emits `AUTHORIZATION_CONSUMED`; the second
  transaction sees `CONSUMED` and raises `ExecutionAuthorizationConflictError`
  (fail-closed DENY). Result: **at most one valid claim**.

## 15. Expiry

- `expires_at` is **mandatory for human-issued authorizations**; system/policy
  low-risk scopes MAY set `expires_at = null` only when a separate policy gate
  explicitly permits open duration (rare; policy-version-bound).
- Authoritative clock: monotonic local system clock; persisted `issued_at` /
  `expires_at` are ISO-8601.
- Expiry after claim but before execution: the claim is invalidated; a new
  authorization is required (claims do not extend expiry).
- After execution begins: in-flight execution is permitted to complete under its
  already-validated claim; expiry does not abort a started, claimed execution.
- Renewal: requires a new `ExecutionAuthorizationRequest` (no silent extension).

## 16. ExecutionClaim

**REQUIRED.** An immutable/transactional `ExecutionClaim` sits between
authorization and execution:

```text
ExecutionAuthorization → atomic claim → ExecutionClaim → worker routing
```

Fields: `claim_id`, `authorization_id`, `task_id`, `attempt_number`,
`claimed_at`, `worker_identity` (assigned at claim), `claim_hash`. Benefits:
prevents replay, provides at-most-once semantics, separates authorization from
consumption, creates an audit event before any worker runs. The worker/router
receives the `claim_id` + `claim_hash` as proof authority was validated — it
does NOT re-derive authority from `governance.accepted`.

## 17. Worker handoff

```text
governance → authorization service → validated execution claim → worker router → worker
```

The router validates the `ExecutionClaim` (claim hash, not-expired, not-revoked,
scope match) and passes the validated claim to the worker. The worker must never
query `governance.accepted` and infer authority. Aligns with ARCH-EXECUTION's
envelope (`authorization_sha256`, `parent_acceptance_sha256`).

## 18. Crash recovery

- Authorization claimed (`EXECUTION_CLAIMED`) → process crashes → worker never
  starts.
- The claim is **permanently consumed** (ledger `CONSUMED`/claim row written
  atomically with claim). For single-use, no retry without new authorization.
- For `attempt_limit = N` bounded-retry: a crashed claim counts as one attempt;
  the next attempt requires a new `ExecutionClaim` against the same
  authorization until attempts exhausted.
- Deterministic recovery: re-read ledger; if `EXECUTION_CLAIMED` exists without
  `EXECUTION_STARTED`, treat as consumed attempt; no silent re-claim.

## 19. ExecutionAttempt

**REQUIRED** as a first-class persisted object for auditable retries:

```text
execution_attempt_id, authorization_id, claim_id, task_id,
attempt_number, started_at, completed_at, result, failure_class, worker_identity
```

Decided required (not optional) because crash-recovery + bounded-retry auditing
depend on it; avoids hidden retry state.

## 20. Retry authorization

- Default: **each retry requires a distinct `ExecutionClaim`** against the same
  authorization until `attempt_limit` is reached (bounded-retry model).
- Single-use (`attempt_limit = 1`): any failure requires **new authorization**.
- Least-authority preference: prefer bounded-retry for resilient低风险 scopes;
  single-use for high-impact operations.

## 21. Input / acceptance binding

`accepted_governance_hash` (the `AcceptanceArtifact.acceptance_sha256`) is bound
into `ExecutionAuthorization`. If underlying inputs change after acceptance, the
old authorization's `accepted_governance_hash` no longer matches current
acceptance → validation fails (threat #2/#8). `authorized_scope.input_hash`
binds the exact operation inputs; a caller presenting a different input hash is
DENIED. Authorization becomes invalid if operation or accepted input identity
drifts.

## 22. Operator / human approval considerations

Before granting, the operator sees: `task_id`, governance state (`ACCEPTED`),
`acceptance_artifact_id` + hash, operation being authorized, scope, worker/target,
risk classification, `expires_at`, retry allowance (`attempt_limit`). Design only;
no UI in this milestone.

## 23. Failure semantics

- `NO AUTHORIZATION EXISTS` (task not yet authorized) is distinct from
  `AUTHORIZATION EXISTS BUT FAILS INTEGRITY`.
- The latter raises `ExecutionAuthorizationIntegrityError` (new, distinct from
  `GovernanceIntegrityError` — domains are separate). It is NOT downgraded to a
  business "not authorized" miss.
- Validation seam (future): `validate_execution_authorization(task_id,
  requested_operation, authorization_id) -> ExecutionPermission` returning
  `{authorized, authorization_id, task_id, scope, expires_at,
  remaining_attempts, governance_acceptance_hash}` — never a bare
  `can_execute(task_id) -> bool`.

## 24. Test strategy (future implementation)

- Unit: artifact immutability + hash binding; store record/get/consume/revoke.
- Negative: all 10 threat cases (§4) as explicit DENY/integrity-failure tests.
- Replay: consume twice → second fails.
- Concurrency: two simultaneous claims → exactly one succeeds (DB transaction).
- Expiry/revocation: expired/revoked → DENY; tampered ledger → integrity error.
- Integration: `ReviewRunnerStub.prepare()` stays governance-only; a separate
  `ExecutionAuthorizationService` integration test proves `ACCEPTED` alone does
  not yield a claim.

## 25. Implementation phases

- **EA-1** Execution Authorization domain model + schemas (artifact, request,
  decision, claim, attempt).
- **EA-2** `ExecutionAuthorizationStore` + `ExecutionAuthorityLedger` (separate
  DB) + integrity errors.
- **EA-3** Authorization decision/issuance service (human + policy paths).
- **EA-4** Atomic `ExecutionClaim` + concurrency/consume.
- **EA-5** Read-only integration into existing orchestration (no authority).
- **EA-6** Worker-router handoff (validated claim → envelope).
- **EA-7** End-to-end proof + negative/replay/concurrency tests.

**EA-3 is the first phase that introduces real execution-capability issuance.**
It requires a separate, explicit user authorization before implementation
(per this milestone's stop condition). EA-1/EA-2 are pure model/persistence and
still forbidden from issuing authority.

## 26. Explicit unresolved questions

- Final clock-sync policy for `expires_at` across multi-process deployments
  (local monotonic clock assumed for v1).
- Exact policy thresholds distinguishing human-required vs system-eligible
  scopes (left to the EA-3 policy service design).
- Whether `automation_state.db` later hosts any execution *runtime* state (out of
  scope; if so, defined explicitly, never as authorization truth).

## Final recommendation

Adopt the three-domain separation (Governance / Execution Authority / Execution
Runtime). Issue `ExecutionAuthorization` from a **separate authority domain**
persisted in a **separate `execution_authority.db`**, bound by hash to the
immutable `AcceptanceArtifact`. Enforce single-use/atomic claims, expiry,
revocation, input-mutation protection, and fail-closed integrity. Workers receive
validated `ExecutionClaim`s, never derived authority. This preserves
`ACCEPTED != EXECUTION AUTHORIZATION` and extends ADR-0004 without weakening any
Phase 6 boundary.
