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
identity, timestamp (**absolute UTC RFC 3339 / ISO-8601**; see §15), artifact
hash. Replay
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

- `issued_at` and `expires_at` are persisted as **absolute UTC RFC 3339 /
  ISO-8601 timestamps** (e.g. `issued_at = 2026-08-12T21:30:00Z`,
  `expires_at = 2026-08-12T22:00:00Z`). They are the authoritative, auditable
  source of truth across application restart, machine reboot, persisted
  authorization reload, and multi-process audit reconstruction.
- **Clock distinction (mandatory):**
  - *Persisted / auditable time* = absolute UTC wall-clock timestamp.
  - *Optional in-process elapsed-time enforcement* = a monotonic clock MAY be
    used only for measuring elapsed time **after** an authorization has been
    loaded or claimed, never as the persisted source of `issued_at` /
    `expires_at`. A monotonic clock is process/boot-relative and cannot provide a
    stable persisted timestamp.
- `expires_at` is **mandatory for human-issued authorizations**; system/policy
  low-risk scopes MAY set `expires_at = null` only when a separate policy gate
  explicitly permits open duration (rare; policy-version-bound).
- **Validation:** `trusted_current_utc >= expires_at` → authorization expired
  (DENY). Use a trusted current UTC source, not a boot-relative monotonic value.
- **Clock-failure semantics (fail-closed):** if authorization validation cannot
  establish valid time — clock unavailable, timestamp unparsable,
  `expires_at < issued_at`, or a material clock rollback is detected where
  detectable — then **do not authorize execution**; raise an explicit
  authorization-validation / integrity error. Malformed expiration metadata is
  NEVER silently treated as an unexpired authorization.
- **Before `ExecutionClaim`:** authorization expiration blocks creation of a
  claim (`expires_at` must be in the future at claim time).
- **After a valid atomic `ExecutionClaim`:** the authorization has already been
  consumed for that claim. Subsequent expiration does **not** retroactively
  invalidate an already-issued claim. Whether a claimed-but-not-started execution
  has its own claim/start deadline belongs to `ExecutionClaim` policy, not
  authorization expiration (see §16). `ExecutionAuthorization.expires_at` must
  NOT be overloaded to govern both issuance/claim eligibility and execution
  runtime; if needed, introduce a separate `claim_expires_at` / `must_start_by`
  on the claim.
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

- Final clock-sync policy for `expires_at` across multi-process deployments:
  persisted timestamps are absolute UTC (§15); the only open question is which
  trusted UTC source / skew-tolerance governs `trusted_current_utc` comparison
  (single-machine local UTC acceptable for v1; NTP/authorized-time source for
  distributed deployment). Monotonic clocks remain in-process elapsed-time only.
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

## 27. Implementation status (EA-1)

**EA-1 is COMPLETE (domain model + schemas only).** Commit: local `main`,
authored `Add Hermes execution authorization domain model`.

Implemented:

- `tools/hermes_core/execution_authorization.py` — immutable frozen dataclasses
  `ExecutionAuthorization`, `ExecutionAuthorizationRequest`,
  `ExecutionAuthorizationDecision`, plus structured `ExecutionAuthorizationScope`,
  `ExecutionAuthorizationActor`, `ExecutionAuthorizationPolicyRef`; `(str, Enum)`
  `ExecutionAuthorizationActorType` (HUMAN / POLICY_SERVICE / SYSTEM) and
  `ExecutionAuthorizationDecisionOutcome` (GRANTED / DENIED).
- Deterministic canonicalization reused from `tools/hermes_core/hashing.py`
  (`canonical_json` + `sha256_payload`); `artifact_hash` excludes itself;
  `to_canonical_dict()` / `canonical_json()` / `verify_hash()` semantics mirror
  `AcceptanceArtifact`.
- Pure builders (`build_execution_authorization[_request|_decision]`), domain
  validation, and hash verification. Bare `task_id` is never sufficient:
  `accepted_governance_artifact_id` + `accepted_governance_hash` are required.
- `(str, Enum)` actor type and decision outcome are constrained; GRANTED requires
  `authorization_id`, DENIED forbids it (cross-field invariant enforced).
- YAML schemas `docs/architecture/schemas/execution-authorization*.schema.yaml`
  (distinct schema names `hermes.execution_authorization[_request|_decision]`,
  no collision with legacy `hermes.authorization`). Validated via
  `SchemaCatalog.validate()`.
- 39 focused tests green (domain + schema parity + hashing + negative + safety).
- Mutation tooth: a DENIED decision permitted to carry `authorization_id`
  breaks the targeted invariant; source restored byte-exactly.

**NOT implemented (by design):**

- `execution_authority.db` / `ExecutionAuthorizationStore` / `SQLite` persistence.
- Authorization issuance / grant / revocation persistence.
- `ExecutionClaim` / `ExecutionAttempt` / `WorkerRouter`.
- Worker launch / enqueue / dispatch.
- `AUTHORIZED_FOR_EXECUTION` / `EXECUTING` / `AWAITING_EXECUTION_AUTHORIZATION`
  transitions.
- `ExecutionAuthorizationIntegrityError` (introduced in EA-2 for persisted-tamper
  semantics); EA-1 uses only `ExecutionAuthorizationError(ValueError)` /
  `ExecutionAuthorizationValidationError(ValueError)`.

**Preserved invariant:** `ACCEPTED != EXECUTION AUTHORIZATION`. The artifacts
here are representations only; no production code consumes them to grant
authority. `app.py` unchanged; `automation_state.db` untouched.

**Schema-engine limitation (documented):** the shared `SchemaCatalog` validator
does not enforce `minimum` on integer-typed fields and does not require a
trailing `Z` for `date-time`. `attempt_limit >= 1` and absolute-UTC timestamps
are therefore enforced in the Python domain model and tested there; the schema
gap is documented, not worked around by weakening Python validation.

## 28. Implementation status (EA-2)

**EA-2 is COMPLETE (persistence + integrity ledger only).** Commit: local `main`,
authored `Add Hermes execution authority persistence`.

Implemented:

- `tools/hermes_core/execution_authorization_store.py` — abstract
  `ExecutionAuthorizationStore` interface plus the EA-2 error hierarchy:
  `ExecutionAuthorizationStoreError(RuntimeError)` →
  `ExecutionAuthorizationIntegrityError` (persisted tamper / chain break, distinct
  from `ExecutionAuthorizationValidationError` and `GovernanceIntegrityError`),
  `ExecutionAuthorizationSchemaError`, `ExecutionAuthorizationConflictError`.
- `tools/hermes_core/sqlite_execution_authorization_store.py` —
  `SQLiteExecutionAuthorizationStore`. Separate `execution_authority.db` (NOT
  governance.db, NOT automation_state.db). Schema version 1 with fail-closed
  version guard. `PRAGMA journal_mode = DELETE` (+ `foreign_keys = ON`,
  `busy_timeout = 5000`), mirroring the governance store.
- Three artifact tables (`execution_authorization_requests`,
  `execution_authorization_decisions`, `execution_authorizations`) storing the
  canonical JSON payload + `artifact_hash`; reconstruction rebuilds nested
  dataclasses/enums via `reconstruct_*` helpers in `execution_authorization.py`.
- Hash verification BEFORE write (`artifact.verify_hash()`) and ON load
  (recompute vs stored `artifact_hash`); corruption raises
  `ExecutionAuthorizationIntegrityError`. Missing record returns `None`
  (distinguishable from corruption).
- Append-only, hash-linked authority ledger (`authority_ledger`) in the same DB;
  `event_id / event_type / artifact_type / artifact_id / artifact_hash /
  payload_sha256 / previous_entry_sha256 / entry_sha256 / timestamp`, mirroring
  repository `LedgerEntry` conventions. Artifact row + ledger event are committed
  transactionally (`BEGIN IMMEDIATE` / rollback on failure). One global chain.
- Idempotent duplicate persistence (identical id + canonical payload → no-op, no
  duplicate ledger event); conflicting immutable artifact →
  `ExecutionAuthorizationConflictError` (never silent overwrite).
- `tools/hermes_core/runtime_config.py` —
  `resolve_execution_authority_db_path()` with `HERMES_EXECUTION_AUTHORITY_DB`
  override → `%LOCALAPPDATA%\Hermes\execution_authority.db`; resolver has NO
  filesystem side effect (parent/database created only at store open).
- `tools/hermes_core/runtime.py` — `get_execution_authorization_store()` provider
  (process-wide cache, test override seams). Returns the store ONLY; grants no
  execution authority, invokes no worker.
- 17 focused EA-2 tests green (persistence, reload/restart proof, idempotent +
  conflict semantics, artifact/ledger tamper, schema-version guard, journal mode,
  resolver side-effect + env override, runtime provider). Full Hermes core suite
  340/340.
- Mutation tooth: disabling the on-load hash check causes the integrity check to
  fail to fire (TOOTH-PASS); restored source re-raises (TARGETED-OK); source
  restored byte-exactly.

**NOT implemented (by design — deferred to EA-3 / later):**

- Authorization issuance service / `grant_execution_authorization(...)` /
  `authorize(...)` / policy evaluation that grants authority.
- `ExecutionClaim` / `ExecutionAttempt` / authorization or attempt consumption.
- Worker routing / launch / enqueue / dispatch.
- `AWAITING_EXECUTION_AUTHORIZATION` / `AUTHORIZED_FOR_EXECUTION` /
  `EXECUTION_CLAIMED` / `EXECUTING` transitions.

**Preserved invariant:** `ACCEPTED != EXECUTION AUTHORIZATION`. The store persists
representations and answers "what was persisted / does it still verify / is the
chain intact" — it never decides whether authority SHOULD be granted. `app.py`
unchanged; `automation_state.db` untouched; governance.db not extended for
execution authority.

## 29. Implementation status (EA-3A domain binding amendment)

**EA-3A is COMPLETE (domain binding amendment only).** Commit: local `main`,
authored `Bind Hermes authorization to request and decision`. No issuance
capability introduced.

Implemented:

- `tools/hermes_core/execution_authorization.py`
  - `ExecutionAuthorizationDecision` gained `request_hash` (64-hex SHA-256 of
    the exact immutable request artifact). It is included in the decision
    canonical preimage and hash-bound.
  - `ExecutionAuthorization` gained `request_id`, `request_hash`,
    `decision_id`, `decision_hash` (all hash-bound in the authorization
    canonical preimage). The cryptographic lineage
    Authorization -> exact Decision -> exact Request -> exact
    AcceptanceArtifact is now complete.
  - Acyclic identity graph (Model A): `decision_id`/`decision_hash` are derived
    from a preimage that EXCLUDES `authorization_id` (which stays a non-hash-bound
    forward linkage). The graph is a strict DAG: Request -> Decision ->
    Authorization.
  - Amended Decision/Authorization artifacts use `artifact_version = "2"`
    (legacy Request artifacts remain at `"1"`); `SUPPORTED_ARTIFACT_VERSIONS`
    now `{ "1", "2" }`.
  - Validation rejects malformed/empty `request_hash` / `decision_hash` and
    empty `request_id` / `decision_id`.
- `docs/architecture/schemas/execution-authorization-decision.schema.yaml` and
  `execution-authorization.schema.yaml` — require the new binding fields.
- `tools/hermes_core/sqlite_execution_authorization_store.py` — reconstruction
  compatibility ONLY: the `execution_authorization_decisions` table gained a
  dedicated `authorization_id` column (the non-hash-bound forward linkage is
  persisted there and re-injected on load) so round-trip reconstruction
  recovers it without polluting the canonical payload/hash. No atomic grant API
  and no request-keyed store extension were added (those belong to EA-3B).
- 16 focused EA-3A binding tests added (hash-binding proofs for all five new
  fields, invalid-binding rejection, round-trip reconstruction, version check,
  acyclic `authorization_id` exclusion, GRANTED/DENIED invariant preservation).

Tests: EA-1 focused 55/55 (39 baseline + 16 EA-3A); EA-2 focused 17/17; schema
9/9; full Hermes core 356/356. Mutation tooth: removing `decision_hash` from the
Authorization builder preimage fails the targeted binding test (TOOTH-PASS);
source restored byte-exactly.

**NOT implemented (by design — deferred to EA-3B / EA-3I):**

- Atomic `record_granted_decision_and_authorization(...)` (EA-3B).
- Request-keyed store reads `get_decision_for_request(...)` /
  `get_authorization_for_request(...)` (EA-3B).
- Authorization issuance service / `grant_execution_authorization(...)` (EA-3I).
- `ExecutionClaim` / `ExecutionAttempt` / worker routing / `AUTHORIZED_FOR_EXECUTION` /
  `EXECUTING` (later phases).

**Preserved invariant:** `ACCEPTED != EXECUTION AUTHORIZATION`.

## 29.1 EA-3A persistence-integrity correction (amended into the same commit)

Pre-push review of `9b3dc96` found two persistence-integrity gaps from the new
non-hash-bound `Decision.authorization_id` storage. Both corrected; the
correction is amended into the single EA-3A commit (no follow-on commit).

Problem 1 - schema version drift. EA-3A added physical columns
(`authorization_id`, `decision_linkage_sha256`) to
`execution_authorization_decisions` but left `SCHEMA_VERSION = 1`. A physical
schema change must not silently keep the same version. Chosen strategy: **A**
(bump to v2, fail-closed on v1; no silent migrate). `SCHEMA_VERSION` is now `2`,
`SUPPORTED_SCHEMA_VERSIONS = {2}`. Opening a pre-EA-3A (EA-2) schema-v1 DB
whose decisions table lacks the new columns raises
`ExecutionAuthorizationSchemaError` (unsupported old schema, pending a
separately authorized migration). `CREATE TABLE IF NOT EXISTS` never runs
against an unknown/old DB.

Problem 2 - `authorization_id` tamper gap. The column was not hash-bound, so
direct SQL tampering of `execution_authorization_decisions.authorization_id`
was accepted by `get_decision` and `verify_integrity`. Corrected with a
separately hash-bound persistence envelope: `decision_linkage_sha256 =
sha256_text(canonical_json({decision_id, authorization_id}))`, stored in a new
NOT NULL column and verified on load and during `verify_integrity`. The
Decision artifact hash stays acyclic (envelope does not feed it); the persisted
linkage is now tamper-evident, including DENIED (`authorization_id = NULL`).

Tests added (EA-2 store, 5): GRANTED linkage SQL tamper detected on `get_decision`
and on `verify_integrity`; DENIED linkage SQL tamper (NULL -> valid id)
detected on both paths; pre-EA-3A schema-v1 DB fails closed; default schema
version is 2.

Identity DAG preserved: Request -> Decision -> Authorization (acyclic).
No issuance API, no atomic grant API, no request-keyed reads, no
`ExecutionClaim`/`ExecutionAttempt`, no worker behavior. Not pushed.

## 29.2 EA-3B atomic store amendment (implementation, COMPLETE)

**EA-3B is COMPLETE (persistence-contract strengthening only).** Commit: local
`main` only (not yet pushed — push requires a separate pre-push audit +
remote checkpoint authorization, per the EA-3B milestone authorization).

- New atomic store method `record_granted_decision_and_authorization(decision,
  authorization)` persists a GRANTED decision and its `ExecutionAuthorization`
  in a single SQLite transaction (BEGIN IMMEDIATE -> decision row +
  DECISION_RECORDED -> authorization row + AUTHORIZATION_RECORDED -> COMMIT).
  Any failure rolls back with zero residue.
- Fail-closed cross-artifact consistency checks (storage-only; does NOT decide
  authority): `decision.outcome == GRANTED`, `authorization_id`, `request_id`,
  `request_hash`, `decision_id`, `decision_hash`, `task_id`, policy reference,
  and acceptance binding (request <-> authorization).
- Request prerequisite: the referenced `ExecutionAuthorizationRequest` must
  already be persisted; its hash and task identity must agree with the decision.
- Standalone `record_decision(GRANTED)` and `record_authorization()` are now
  REJECTED (half-grant / orphan-authorization bypass eliminated). DENIED
  decisions persist via `record_decision` (one terminal decision per request).
- Request-keyed reads: `get_decision_for_request(request_id)` and
  `get_authorization_for_request(request_id)` query by physical `request_id`
  with integrity-verified reconstruction; missing -> None, multiple -> fail
  closed.
- `UNIQUE(request_id)` on decisions and authorizations enforces one terminal
  decision per request and one authorization per request. Identical grant
  replay is idempotent; conflicting replay fails closed; DENIED-then-grant is
  blocked (EA-3D requires a new request after denial).
- `request_linkage_sha256` tamper envelope (decisions + authorizations);
  verified on load and in `verify_integrity`. Physical `request_id` tampering
  is detected on read and on `verify_integrity`.
- `verify_integrity()` extended: physical request_id == canonical request_id;
  uniqueness invariants; orphan detection (GRANTED decision without
  authorization, authorization without GRANTED decision).
- Authority DB schema bumped `2 -> 3`. Physical change: `request_id` columns
  (UNIQUE) + `request_linkage_sha256` on decisions and authorizations. Opening
  a pre-EA-3B (EA-3A) schema-v2 DB, or a pre-EA-3A schema-v1 DB, fails closed
  (`ExecutionAuthorizationSchemaError`). NO silent migration, NO auto-migrate.
- Tests: 18 new EA-3B store tests (atomic success, mismatch matrix,
  zero-write guarantee, missing/wrong request, denied-then-grant, idempotent /
  conflicting replay, request-keyed read + tamper, rollback-injection
  zero-residue, standalone bypass elimination, DENIED standalone, orphan
  detection, concurrency). Plus 2 schema-version tests. Two mutation teeth
  (decision_hash cross-check removal; rollback commit split) pass with
  byte-exact restore. Full hermes_core suite: 379/379.

**Preserved invariant:** `ACCEPTED != EXECUTION AUTHORIZATION`. The store
validates cross-artifact consistency only; it does not evaluate governance
acceptance, actor authority, authorization policy, expiry, or nonce, and it
creates no claim, attempt, or worker behavior. No issuance service exists.
