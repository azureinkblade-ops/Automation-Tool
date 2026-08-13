# Hermes Execution Authorization Issuance Design (EA-3D)

Status: DESIGN ONLY. No production Python is introduced by this document.
Authorized separately as EA-3D. EA-3I (implementation) requires its own
explicit authorization.

EA-3A COMPLETE (2026-08-13): the domain binding amendment is implemented and
verified. `ExecutionAuthorizationDecision` now carries `request_hash`;
`ExecutionAuthorization` now carries `request_id`, `request_hash`,
`decision_id`, `decision_hash`. Cryptographic lineage is
Authorization -> exact Decision -> exact Request -> exact AcceptanceArtifact.
Amended Decision/Authorization artifacts use `artifact_version = "2"`; the
Decision's `authorization_id` is intentionally excluded from its hash preimage
(acyclic Model A) and persisted in a dedicated store column (plus a
tamper-evident `decision_linkage_sha256` envelope) for round-trip
reconstruction. Authority DB schema is versioned `2`; a pre-EA-3A v1 DB fails
closed (no silent migration). No issuance API, atomic grant API, or
request-keyed store extension was added (those belong to EA-3B). The
persistence-integrity correction is amended into the same EA-3A commit.

EA-3B COMPLETE (2026-08-13): storage-only atomic store amendment, no issuance
capability. New `record_granted_decision_and_authorization(decision,
authorization)` persists a GRANTED decision and its authorization in a single
SQLite transaction (DECISION_RECORDED then AUTHORIZATION_RECORDED, no unrelated
event between), with fail-closed cross-artifact consistency checks (outcome,
authorization_id, request_id, request_hash, decision_id, decision_hash,
task_id, policy reference, acceptance binding) and a request prerequisite
(persisted request must exist, request hash and task identity must agree).
Standalone `record_decision(GRANTED)` and `record_authorization()` are now
rejected (bypass eliminated); DENIED decisions persist via `record_decision`.
New `get_decision_for_request(request_id)` and
`get_authorization_for_request(request_id)` read by physical `request_id` with
integrity-verified reconstruction. UNIQUE(request_id) enforces one terminal
decision per request and one authorization per request; replay of an identical
grant is idempotent, conflicting replay fails closed. A `request_linkage_sha256`
tamper envelope covers decisions and authorizations. `verify_integrity()`
extends to request_id physical-vs-canonical checks, uniqueness invariants, and
orphan detection (GRANTED decision without authorization, authorization without
GRANTED decision). Authority DB schema is now version `3`; v1/v2 fail closed
(no silent migration). Tests: 18 new EA-3B store tests; mismatch matrix,
rollback-injection zero-residue, request_id tamper, orphan detection, schema
version, concurrency, idempotency, and two mutation teeth (decision_hash check,
rollback split) all green. The absolute invariant `ACCEPTED != EXECUTION
AUTHORIZATION` is preserved.

EA-3I.1 COMPLETE (2026-08-13): pre-capability policy + authority evaluation
contracts, **no real `ExecutionAuthorization` created or persisted**. New
modules `tools/hermes_core/execution_authorization_policy.py` (deterministic,
versioned `ExecutionAuthorizationPolicy` model + registry loaded from
`tools/hermes_core/policies/*.yaml`; `resolve_policy` fails as
`ExecutionAuthorizationPolicyNotFoundError` / `...VersionError`, never as DENY)
and `tools/hermes_core/execution_authorization_evaluation.py` (pure/read-only
`evaluate_execution_authorization_policy`, `ExecutionAuthorizationActorContext`
separating identity/authentication/authority, structured
`ExecutionAuthorizationEvaluationResult` / `ExecutionAuthorizationPolicyEvaluation`
with NO capability-bearing identifiers). Explicit
`ALLOW` / `DENY` / `REQUIRES_HUMAN` decision enum. Authority-principal posture:
HUMAN eligible only when authenticated + recognized role; POLICY_SERVICE
requires explicit human decision unless an operation/worker_class is enumerated
in `auto_scopes` (default NONE); SYSTEM can never grant by default (DENY).
Unknown operation / unknown worker_class fail closed (DENY); `worker_class =
None` is deferred/unresolved, not unrestricted (REQUIRES_HUMAN). Attempt/runtime
ceilings constrain, never widen. Read-only `verify_acceptance_prerequisite`
checks request acceptance binding against an already-loaded `AcceptanceArtifact`
(no governance.db access, no mutation); ACCEPTED is prerequisite only, not
authorization. Deterministic: identical immutable inputs yield identical
results. No DB writes, no EA-3B atomic-grant call, no claim/worker/execution.
19 focused tests; three mutation teeth (POLICY_SERVICE default -> ALLOW, remove
role validation, scope widening) all kill a targeted test with byte-exact
restore. Full hermes_core suite: 398/398. The absolute invariant `ACCEPTED !=
EXECUTION AUTHORIZATION` is preserved.

This document freezes the trust boundary and issuance contract before any
callable component can create a real `ExecutionAuthorization`. It is grounded in
the implemented EA-1 domain model and EA-2 persistence layer and does not
introduce behavior that conflicts with them.

## 1. Purpose

Define exactly who may create an `ExecutionAuthorization`, from what evidence,
under what policy, with what atomicity and integrity guarantees, and with what
fail-closed behavior. The goal is to make the first real authority-creating
slice (EA-3I) unambiguous and auditable.

## 2. Existing EA-1/EA-2 baseline

- EA-1 provides the immutable domain artifacts: `ExecutionAuthorizationRequest`,
  `ExecutionAuthorizationDecision`, `ExecutionAuthorization`, plus
  `ExecutionAuthorizationScope`, `ExecutionAuthorizationActor`,
  `ExecutionAuthorizationPolicyRef`. Hashing is canonical and reused from
  `tools/hermes_core/hashing.py`.
- EA-2 persists them in a separate `execution_authority.db`, verifies integrity
  on load, and maintains an append-only hash-linked authority ledger
  (`REQUEST_RECORDED` / `DECISION_RECORDED` / `AUTHORIZATION_RECORDED`).
- No issuance, claim, worker, or execution transition exists yet.

## 3. Non-goals

EA-3D does not design claims, attempts, worker routing, execution dispatch, or
consumption. It stops at the durable, integrity-verified `ExecutionAuthorization`.
`ACCEPTED != EXECUTION AUTHORIZATION` remains absolute.

## 4. Trust boundary

```
Governance
    -> AcceptanceArtifact

ExecutionAuthorizationRequest
    -> EA-3 Authorization Service
         - validate acceptance binding
         - validate request integrity
         - validate actor identity / authority
         - resolve policy
         - evaluate requested scope
         - produce DENIED decision
         - produce GRANTED decision + ExecutionAuthorization
              -> EA-2 persistence + ledger
         STOP
```

`ExecutionAuthorization issued` != `ExecutionClaim` != `execution started`.

## 5. Authority principals

The architecture selected a HYBRID authority model. Principal categories:

- `HUMAN` -- an operator with an authenticated session and an authority role.
- `POLICY_SERVICE` -- an automated policy evaluator (no human in the loop).
- `SYSTEM` -- internal/system context (records events, may request, does not grant).

### Authority principal matrix

```
Actor type      May request   May decide   May issue   Scope limits
--------------------------------------------------------------------
HUMAN           YES           YES          YES          bounded by role + policy
POLICY_SERVICE  YES           YES          YES*         ONLY explicitly allowed scopes
SYSTEM          YES (internal) NO           NO           n/a
```

`*` -- `POLICY_SERVICE` may issue ONLY for scopes enumerated as auto-issuable
(see section 24). All other scopes require `HUMAN`. `SYSTEM` may never grant
authority.

## 6. Identity / authentication model

Possessing `actor_id` is insufficient. Distinction:

- `identity` -- who the actor is (`actor_id`).
- `authentication` -- how the actor was verified (`authentication_context`).
- `authority role` -- what the actor is permitted to decide (`authority_role`).
- `authorization policy` -- which policy governs the decision (`policy_id`/`version`).

Rule: `actor authenticated AND possesses required authority_role AND policy
permits that role for requested scope -> may decide`. `actor_type == HUMAN` does
NOT automatically authorize.

`authentication_context` holds NON-SECRET references only: authentication
mechanism, verified session reference, operator-console session id, or
identity-provider assertion id. It must NOT contain password, API key, bearer
token, session secret, or private key. Evidence is referenced externally;
future implementation verifies it through a stable authentication seam. It is
embedded in the artifact (record) but never contains secret material.

## 7. Request prerequisite

Every issuance MUST begin from an existing persisted
`ExecutionAuthorizationRequest`.

```
no request -> no decision -> no authorization
```

No exceptional system path skips requests. `SYSTEM` may create internal
requests but still flows through the same decision/issuance path.

## 8. Acceptance verification

A request binds to immutable governance acceptance via
`accepted_governance_artifact_id` + `accepted_governance_hash`. Verification
flow:

1. load request; `request.verify_hash()` MUST be True.
2. load referenced `AcceptanceArtifact` via governance runtime/store API.
3. verify acceptance artifact integrity (`acceptance_sha256` matches).
4. verify `acceptance_id` matches `accepted_governance_artifact_id`.
5. verify `acceptance_sha256` matches `accepted_governance_hash`.
6. verify governance terminal state is `ACCEPTED`.

`ACCEPTED` is only a prerequisite. It is not authority.

## 9. Cross-store verification

Approach selected: **A. governance runtime/store API**. EA-3 must use the
existing governance provider (`get_governance_store()` /
`get_task_governance_status()` / `verify_governance_integrity()`) rather than
opening raw governance SQLite tables. This keeps governance DB separate and
uses a stable domain API.

## 10. Acceptance substitution defense

Threat: request references task A but acceptance from task B is substituted.
Defense: `task_id`, `acceptance_id`, `acceptance_sha256` MUST match across
request, acceptance artifact, decision, and authorization. Any mismatch fails
closed. The request carries its own `task_id`; it must equal the
`AcceptanceArtifact.task_id` and the decision/authorization `task_id`.

## 11. Request integrity

Before decision: `request.verify_hash() == True` is required. If the persisted
request is corrupt, `ExecutionAuthorizationIntegrityError` MUST propagate. A
corrupt request is NEVER reinterpreted as denied. Distinctions preserved:
request invalid vs request missing vs request denied.

## 12. Request status model

No first-class mutable request state is introduced in EA-3. Decision history is
append-only (ledger). Recommendation: keep request as immutable artifact +
immutable decision artifacts; do not add a mutable `PENDING/DECIDED/CANCELLED/
EXPIRED` column. If status display is needed, derive it from the decision
ledger.

## 13. Decision prerequisite

Authorization issuance MUST always be preceded by
`ExecutionAuthorizationDecision(outcome=GRANTED)`.

```
Request -> Decision(GRANTED) -> ExecutionAuthorization
```

Never `Request -> ExecutionAuthorization` directly. A `DENIED` decision MUST
NEVER lead to an authorization.

## 14. Decision / authorization atomicity

The `GRANTED` decision and the `ExecutionAuthorization` MUST be persisted
atomically (one transaction). Durable states avoided:
- `GRANTED` decision exists but authorization missing.
- authorization exists without durable `GRANTED` decision.

See section 45 for the store extension.

## 15. Who constructs the authorization

The issuance service constructs the `ExecutionAuthorization`. The caller
supplies a `Request`; the service validates request/evidence/policy, constructs
the `Decision`, and constructs the `ExecutionAuthorization`. The caller never
manufactures the authority artifact that the service rubber-stamps.

```
caller -> ExecutionAuthorizationRequest
EA-3 service -> validates -> constructs Decision -> constructs ExecutionAuthorization
```

## 16. Caller-controlled fields

Caller controls:

- requested `operation`
- requested `input_hash`
- requested `worker_class`
- requested `max_runtime`
- requested `attempt_limit`
- request reason

The service MAY accept, reduce, or reject each. The service MUST NEVER silently
increase authority beyond the request.

Invariant: `issued scope <= requested scope`.

## 17. Scope narrowing

Rules (enforced by policy + service):

- requested `attempt_limit` = 3, policy max = 1 -> issue 1 or deny.
- requested `max_runtime` = 3600, policy max = 600 -> issue 600 or deny.
- requested `worker_class` = X, policy permits only Y -> deny.

Issued scope never exceeds request.

## 18. Scope dimensions

Authorization checks enforced for: `operation`, `worker_class`, `input_hash`,
`attempt_limit`, `max_runtime_seconds`. Additional dimensions (environment,
model/provider, filesystem roots, network permission, output destination) are
NOT added in EA-3; they are flagged as future scope dimensions requiring
explicit justification.

## 19. Input immutability

`input_hash` binds the exact future execution input. The bytes/document hashed
are the canonical execution input manifest; canonicalization follows the
repository's canonical hashing. Hash is computed by the requestor at request
time and bound into the request artifact. Issued authorization remains valid
only while `input_hash` matches; a changed input invalidates the authorization
at claim time (EA-4 concern, not EA-3).

## 20. Worker class validation

`worker_class = None` does NOT mean unrestricted. It means worker selection is
deferred but constrained by the operation's registered worker catalog. EA-3
validates the requested `worker_class` against policy/catalog metadata; `None`
is permitted only when the operation's policy explicitly allows deferred
selection, and the claim layer (EA-4) still binds a concrete worker before
execution.

## 21. Operation identifiers

Operations MUST be drawn from a registered operation catalog / explicit
allow-list (e.g. `stage2-v1-gpu-execution`, `chapter-promo-render`,
`social-post-generation`). Free-form semantics are prohibited. The policy
references the operation by canonical id.

## 22. Policy selection

The service resolves the applicable policy; the caller does not choose arbitrary
`policy_id`. Selection is deterministic from `actor_role`, `operation`, `scope`,
`environment`. The request MAY suggest a policy, but the service validates or
overrides it by deterministic rules.

## 23. Policy immutability

Once authorized, `policy_id` + `policy_version` permanently identify the policy
used. Future policy changes do NOT retroactively reinterpret an already-issued
authorization.

## 24. Policy implementation location

Policy definitions live as versioned data / repository documents / SQLite table
(deterministic, versioned), not hidden mutable UI-only state.

## 25. Policy evaluation result

Evaluation returns an explicit model: `ALLOW` / `DENY` / `REQUIRES_HUMAN` +
constrained scope. This matters for hybrid authority (a `REQUIRES_HUMAN` result
cannot auto-issue).

## 26. Human-only scopes

Scopes that can NEVER be auto-issued by `POLICY_SERVICE`:

- first-time worker type
- new operation (not in catalog)
- network-enabled execution
- filesystem write outside bounded workspace
- high runtime / resource ceilings (above policy threshold)
- multiple attempts (attempt_limit > 1)
- production publishing
- destructive actions

## 27. Policy-service scopes

Default auto-issuable set for `POLICY_SERVICE` is **NONE** until explicit
low-risk scopes are documented with deterministic criteria. If automated
issuance is later allowed, enumerate exact categories. No catch-all
(`LOW_RISK`) without deterministic criteria.

## 28. SYSTEM actor semantics

`SYSTEM` may request / record internal events but MUST NOT grant authority.
`SYSTEM` is never a deciding/issuing principal.

## 29. Human actor semantics

Human authorization is represented by `actor_id`, `authority_role`,
`authentication_context`, `decision_reason`. Approval is an explicit user action
(explicit CLI confirmation, authenticated UI approve action, signed operator
command). Passive viewing is NOT approval.

## 30. Explicit approval semantics

Human approval MUST be affirmative. The following are NOT approval: request
created, request opened, request not denied, timeout.

```
explicit approval action -> GRANTED decision
```

## 31. Denial semantics

A denial produces `ExecutionAuthorizationDecision(outcome=DENIED)` with reason.
Denial MUST NOT alter governance acceptance. `governance remains ACCEPTED;
authorization decision = DENIED`. This reinforces `content/governance approval
!= execution authority`.

## 32. Reconsideration after denial

Recommendation: a denied request requires a NEW request. Submitting the same
request id again MUST be blocked (one terminal decision per request, section
49). This keeps decision history deterministic.

## 33. Duplicate request handling

EA-2 already persists identical request artifacts idempotently. Issuance
behavior if the same request is processed twice: if an existing terminal
decision is found, return the existing decision/result; never issue a second
authorization.

## 34. Replay protection

Binding keys: `request_id`, `decision_id`, `authorization_id`, `nonce`. Same
request replayed, same approval replayed, same human command replayed are
handled by the one-decision-per-request invariant and immutable artifacts.
Nonces provide per-issuance replay identity.

## 35. Authorization uniqueness

One request yields exactly one authorization (when GRANTED). Retries use a new
request or explicitly separate retry authorization, not duplicate issuance from
the same request.

## 36. Expiry selection

`expires_at` is chosen as: request may ask for a duration; policy constrains max
duration; service sets `issued_at` (current UTC) and computes `expires_at`.
Persisted time is absolute UTC `Z`. No monotonic persisted time.

## 37. Null expiry

`expires_at = None` is PROHIBITED in initial EA-3. Only a human-only explicit
policy exception (future, separately authorized) may permit it. Initial posture:
deny issuance if `expires_at is None`.

## 38. Clock source

EA-3I uses an injectable clock seam: `now_utc()` pure callable (or
`Clock.now_utc()`). Tests must not depend on real wall-clock time. No monotonic
time for persisted timestamps.

## 39. Clock failure

Clock unavailable, invalid UTC, or detectable material rollback -> issuance MUST
fail (no authorization created). Fail-closed.

## 40. Nonce generation

The issuance service generates `nonce` (not the caller). Recommendation:
cryptographically random, hex, unique per authorization. Nonce is replay
identity, not a credential; no secret value required.

## 41. Authorization ID / Decision ID construction

EA-3 reuses EA-1 deterministic builder semantics for `authorization_id` and
`decision_id`. No second ID algorithm is introduced.

## 42. Reason requirements

- `request_reason`: required, non-empty.
- `decision_reason`: required; for human decisions non-empty; for policy grants
  identifies deterministic policy outcome (e.g. `policy ea-low-risk-v2 rule
  R-004 matched`). No secrets.

## 43. Failure taxonomy

Distinguish at minimum:

- request not found
- request structurally invalid
- request integrity corrupt
- acceptance missing
- acceptance integrity corrupt
- acceptance binding mismatch
- governance not ACCEPTED
- actor unauthenticated
- actor unauthorized
- policy not found
- policy unsupported version
- policy denied
- human approval required
- scope invalid
- scope exceeds policy
- persistence conflict
- persistence integrity error
- clock failure

Not all collapsed into `authorization failed`.

## 44. Denial vs error

`DENIED` = a valid decision not to grant. Errors (corrupt request/acceptance,
invalid policy, DB integrity failure) are FAILURES, NEVER `DENIED`.

## 45. Fail-closed rule

Any uncertainty about identity, acceptance, policy, scope, time, integrity, or
persistence -> NO AUTHORIZATION ISSUED.

## 46. Persistence atomicity

Future transaction (conceptual):

```
BEGIN IMMEDIATE
verify no prior terminal decision / authorization for request
persist GRANTED decision
persist ExecutionAuthorization
append DECISION_RECORDED ledger event
append AUTHORIZATION_RECORDED ledger event
COMMIT
```

On failure: ROLLBACK. For denial:

```
persist DENIED decision
append DECISION_RECORDED ledger event
COMMIT
```

No authorization row.

## 47. Store API extension design

EA-2 separate `record_decision` + `record_authorization` calls CANNOT guarantee
all-or-nothing across both artifacts. Recommendation: add a dedicated atomic
store method `record_granted_decision_and_authorization(...)`. Denial uses
existing `record_decision(...)`. (Design only; EA-3I implements.)

## 48. Authorization existence query

EA-3I needs `get_decision_for_request(request_id)` and
`get_authorization_for_request(request_id)` for idempotency/replay. EA-2
currently supports `get_decision(decision_id)` / `get_authorization(
authorization_id)` but not request-keyed lookup. A narrow read extension is
specified for EA-3I.

## 49. Request-to-decision uniqueness

Storage invariant: one terminal decision per `request_id`. Enforced by
service+store invariant (and a future unique constraint). Prevents DENIED then
later GRANTED on the same request.

## 50. Request-to-authorization uniqueness

Invariant: at most one authorization per request (when GRANTED). Current
`ExecutionAuthorization` does NOT store `request_id`. See section 53 for the
required amendment.

## 51. Critical domain-gap audit

Current `ExecutionAuthorization` binds `accepted_governance_artifact_id` +
`accepted_governance_hash` (-> AcceptanceArtifact) but does NOT carry
`request_id` or `decision_id`. The link Authorization->Decision is currently
one-way via `ExecutionAuthorizationDecision.authorization_id` only. Without
`request_id`/`decision_id` on the authorization, the chain
Authorization->Decision->Request->Acceptance is not fully cryptographically
bound. Recommendation: AMEND (section 53).

## 52. Decision binding

`ExecutionAuthorizationDecision` carries `request_id` (good) but not
`request_hash`. To prevent request substitution, add `request_hash` to the
decision (binds the exact immutable request). Amendment recommended.

## 53. Authorization binding to decision (DISPOSITION)

**DOMAIN AMENDMENT REQUIRED BEFORE EA-3I.**

`ExecutionAuthorization` MUST gain:

- `request_id: str`
- `request_hash: str` (hash of the immutable request artifact)
- `decision_id: str`
- `decision_hash: str` (hash of the immutable GRANTED decision artifact)

Rationale: a valid authorization artifact that lacks cryptographic binding to
the exact GRANTED decision and request is a substitution risk. This is the single
most important precondition for safe issuance. EA-3D mandates this amendment be
completed (and tests written) before any issuance slice is authorized.

## 54. Threat model

Threat matrix (Threat / Prevention / Detection / Failure / Future test):

- Governance acceptance substitution -> bind acceptance_id+hash+task_id across
  chain; mismatch fails closed. Detection: integrity verify. Test:
  acceptance mismatch fails.
- Request substitution -> request_hash in decision+authorization. Test: tampered
  request rejected.
- Decision substitution -> decision_hash in authorization. Test: decision
  replay rejected.
- Authorization substitution -> authorization_hash verified on load. Test:
  tampered authorization raises IntegrityError.
- Unauthenticated actor -> authentication_context required + verified. Test:
  unauthenticated rejected.
- Unauthorized authority_role -> role check vs scope. Test: wrong role rejected.
- actor_type escalation -> principal matrix enforced. Test: SYSTEM cannot issue.
- Policy substitution -> policy resolved by service, version pinned. Test:
  caller policy override rejected.
- Policy downgrade -> version immutable in evidence. Test: version mismatch
  fails.
- Unsupported policy version -> fail closed. Test: unsupported version fails.
- Requested scope escalation -> issued <= requested. Test: escalation mutant
  killed.
- Issued scope > requested -> service narrows. Test: mutant killed.
- Input mutation -> input_hash bound. Test: input change invalidates.
- Worker-class escalation -> validated vs catalog. Test: disallowed worker
  denied.
- Runtime-limit escalation -> policy max enforced. Test: mutant killed.
- Attempt-limit escalation -> policy max enforced. Test: mutant killed.
- Duplicate request processing -> one decision per request. Test: idempotent.
- Approval replay -> immutable artifacts + nonce. Test: replay blocked.
- Duplicate issuance -> atomic + uniqueness invariant. Test: second auth blocked.
- Expired acceptance context -> acceptance integrity re-verified. Test: stale
  rejected.
- Bad clock -> fail closed. Test: clock failure raises.
- Unbounded expiry -> null expiry prohibited. Test: null expiry rejected.
- GRANTED without authorization -> atomic persistence. Test: transaction tooth.
- Authorization without GRANTED decision -> atomic + decision_id binding. Test:
  mutant killed.
- DENIED followed by authorization -> decision outcome gate. Test: DENIED cannot
  issue.
- Persistence tampering -> EA-2 integrity verify. Test: tamper raises.
- Ledger tampering -> hash chain verify. Test: chain break detected.
- Cross-DB confusion -> separate DBs, hash-reference only. Test: no FK into
  governance.db.
- Authorization triggers worker -> worker boundary enforced (EA-3 has no worker
  import). Test: import scan clean.
- Worker treats ACCEPTED as authority -> ACCEPTED != EXECUTION AUTHORIZATION
  invariant. Test: governance consumer unchanged.

## 55. Security invariants

- I1. ACCEPTED never directly yields ExecutionAuthorization.
- I2. Every issued authorization binds to one verified AcceptanceArtifact.
- I3. Every issued authorization derives from one valid request.
- I4. Every issued authorization corresponds to one GRANTED decision.
- I5. DENIED never produces authorization.
- I6. Issued scope never exceeds requested scope.
- I7. Issued scope never exceeds policy.
- I8. Actor must be authenticated and authorized for the scope.
- I9. Policy ID/version are immutable in issued evidence.
- I10. Issuance is idempotent per request.
- I11. Grant persistence is atomic.
- I12. Issuance never claims or launches a worker.
- I13 (added). Issued authorization cryptographically binds request_id +
  request_hash + decision_id + decision_hash (post-amendment).
- I14 (added). One terminal decision per request_id; one authorization per
  request.

## 56. API design

Future service API (conceptual):

```python
def decide_execution_authorization(
    request_id: str,
    actor_context: ActorContext,
) -> AuthorizationDecisionResult: ...
```

Avoid vague `authorize(task_id)`. The API makes explicit: request identity,
actor context, decision result.

## 57. Result type

Structured, not bare bool:

```python
class AuthorizationDecisionResult:
    request_id: str
    outcome: GRANTED | DENIED
    decision_id: str
    authorization_id: Optional[str]
    policy_id: str
    policy_version: str
    reason: str
```

Errors remain exceptions/failure results, not DENIED outcomes.

## 58. Evaluation vs issuance naming

One orchestration method `decide_execution_authorization(...)` that evaluates
and atomically records the outcome, preventing evaluate-then-bypass. An internal
pure policy evaluator may remain separate.

## 59. Pure policy evaluator

```python
def evaluate_policy(request, actor, acceptance, policy)
    -> ALLOW | DENY | REQUIRES_HUMAN, constrained_scope
```

No DB writes. Issuance orchestration owns persistence.

## 60. Human workflow

1. request exists.
2. UI/CLI loads request + acceptance + proposed scope.
3. operator sees task id, acceptance hash, request id/hash, operation, input
   hash, worker class, attempts, runtime, expiry, policy.
4. operator explicitly APPROVES or DENIES.
5. decision recorded.
6. if approved, authorization issued.

No execution button in EA-3.

## 61. Operator display safety

The human sees exact hash-bound values. Approval UI must not say only "Approve
task?".

## 62. Human approval race

Approval binds to `request_id` + `request_hash` + `policy_version`. If any
change, require new approval (artifacts immutable).

## 63. Policy-service race

Policy evaluation binds to immutable request + explicit policy version.

## 64. Revocation interaction

EA-3 defines issuance-time behavior only. Revocation (future EA-4/other) does not
mutate the authorization artifact; issuance evidence is append-only.

## 65. Expiry interaction

Issuance computes expiration. EA-4 claim checks `now < expires_at`. EA-3 does
not consume the authorization.

## 66. Retry interaction

`attempt_limit` is issued as scope metadata only. EA-4/ExecutionAttempt later
enforces consumption/counting.

## 67. No worker dependency

Future EA-3 service MUST NOT import WorkerRouter, worker classes, subprocess, or
queue implementation. It may validate a worker-class identifier against
policy/catalog metadata, but cannot instantiate or launch workers.

## 68. No execution state transition

EA-3 issuance introduces no execution runtime state. `EXECUTING` is never
touched. `AUTHORIZED_FOR_EXECUTION` is NOT a mutable first-class state in EA-3
(see section 70).

## 69. State ownership

- Governance: UNDER_REVIEW, CONSENSUS_CALCULATED, ACCEPTED.
- Execution Authority: request artifacts, decision artifacts, authorization
  artifacts, authorization lifecycle events.
- Execution Runtime (future): claims, attempts, EXECUTING, results.

No duplicated state across domains.

## 70. AUTHORIZED_FOR_EXECUTION decision

Decision: DERIVED condition (not first-class mutable state). Authorization
existence (valid, unexpired, unrevoked, bound to verified acceptance) is the
evidence. This avoids mutable-state drift. Derived validity is distinct from
claim/consumption.

## 71. Audit queries

Future read-only surface:

- `get_decision_for_request(request_id)`
- `get_authorization_for_request(request_id)`
- `get_authorization_audit_chain(request_id)`

No `can_execute(task_id) -> bool` unless it reports detailed reasons and remains
non-claiming.

## 72. Explainability

Decisions answer: who approved, when, under what policy, what exact scope, what
acceptance, what request, why.

## 73. No secrets in ledger

Ledger events reference actor_id, policy, artifact ids/hashes only. No
credentials.

## 74. Test strategy for EA-3I

At minimum: valid human grant; valid policy-service grant (only if allowed
scopes defined); human-only scope rejected for policy service; unauthenticated
actor rejected; wrong authority role rejected; missing acceptance rejected;
corrupt acceptance fails; acceptance mismatch fails; request corruption fails;
request/acceptance task mismatch fails; policy not found fails; unsupported
policy version fails; policy DENY produces DENIED only; REQUIRES_HUMAN does not
auto-grant; issued scope <= request; issued scope <= policy; expiry bounded;
null expiry rejected; duplicate processing idempotent; second decision blocked;
DENIED cannot later issue; grant transaction atomic; authorization cannot
persist without decision; decision grant cannot persist without authorization;
no worker import/call; no ExecutionClaim.

## 75. Mutation teeth for EA-3I

Mutants to kill:

- ACCEPTED directly returns authorization -> test: acceptance alone rejected.
- actor-role check bypassed -> test: wrong role rejected.
- policy DENY treated as ALLOW -> test: DENIED only.
- issued attempt_limit exceeds request -> test: narrowing enforced.
- input_hash not copied/bound -> test: input bound.
- decision persistence skipped -> test: decision present.
- authorization persisted after DENIED -> test: no auth on deny.
- duplicate request issues second authorization -> test: idempotent.
- authorization lacks decision_hash binding -> test: binding verified.

## 76. Implementation phasing

- EA-3I.1: pure policy evaluation types + actor authority validation.
- EA-3I.2: request/acceptance/decision binding verification.
- EA-3I.3: atomic decision + authorization persistence API (domain amendment +
  store method).
- EA-3I.4: issuance orchestration service.
- EA-3I.5: human-approval adapter / policy-service adapter.
- EA-3I.6: end-to-end issuance proof.

First slice capable of issuing real authority: **EA-3I.3 + EA-3I.4** (atomic
persistence + orchestration). This slice requires separate explicit
authorization AND completion of the domain amendment (section 53).

## 77. Domain amendment gate

DISPOSITION: **EA-1 DOMAIN AMENDMENT REQUIRED** (see section 53). The
Authorization->Decision and Decision->Request cryptographic bindings are not
present today. Do not authorize EA-3I until the amendment ships with tests.

## 78. Persistence amendment gate

DISPOSITION: **EA-2 STORE AMENDMENT REQUIRED**. Add
`record_granted_decision_and_authorization(...)` (atomic) and request-keyed
read queries (`get_decision_for_request`, `get_authorization_for_request`). The
existing separate `record_decision` + `record_authorization` calls are
insufficient for atomic grant issuance.

## 79. ADR requirement

ADR-0014 covers the issuance trust boundary (see
`docs/architecture/decisions/ADR-0014-execution-authorization-issuance-trust-boundary.md`).

## 80. Final recommendation

EA-3D freezes the trust boundary and contract. Before EA-3I is authorized, two
amendments MUST land with tests: (1) EA-1 domain amendment adding
`request_id`/`request_hash`/`decision_id`/`decision_hash` to
`ExecutionAuthorization` (and `request_hash` to `ExecutionAuthorizationDecision`);
(2) EA-2 store atomic method + request-keyed reads. With those in place, EA-3I
slices can create real authority under the fail-closed rules above. Until then,
no `ExecutionAuthorization` is created by production code. (This final
recommendation was written before EA-3I.2 shipped; as of EA-3I.2, real
execution authorization IS created by the issuance service under the contracts
above.)

## 81. EA-3I.2 status (COMPLETE)

**EA-3I.2 COMPLETE (first capability-bearing issuance slice).** Committed as
a single narrow local commit per the EA-3I.2 milestone authorization.

This slice creates REAL execution authority under the EA-3D / EA-3A / EA-3B /
EA-3I.1 contracts:

- Issuance reads an already-persisted `ExecutionAuthorizationRequest`
  (`store.get_request`), verifies its hash, and checks for existing terminal
  evidence before any new issuance (replay idempotency).
- Acceptance is verified exactly via the governance store's
  `load_task_governance_chain(task_id).acceptance`, then
  `verify_acceptance_prerequisite(request, acceptance)` (exact
  acceptance_id + acceptance_sha256 + task_id + `is_accepted()`); bare task_id
  equivalence is insufficient, so acceptance substitution fails with an ERROR
  and zero issuance writes.
- The deciding actor is authenticated and authority-validated; the request's
  requesting actor is never silently substituted for the deciding actor.
- Policy resolves deterministically from the request's exact
  policy_id/policy_version (unknown/unsupported -> ERROR, never silent
  fallback).
- The EA-3I.1 evaluator is reused (no duplicated policy logic). ALLOW /
  DENY / REQUIRES_HUMAN mappings are explicit; REQUIRES_HUMAN never silently
  becomes ALLOW.
- DENY persists a terminal DENIED Decision only (authorization_id None) via the
  safe `record_decision` path.
- ALLOW constructs a matching GRANTED Decision + ExecutionAuthorization using
  the evaluator's constrained scope (never the raw requested scope, never wider)
  and persists only through `record_granted_decision_and_authorization(...)` (EA-3B
  atomic grant, one transaction, rollback zero-residue).
- Clock/expiry/nonce: `issued_at` from an injected UTC clock seam; `expires_at`
  non-null, `> issued_at`, within policy lifetime; clock failure fails closed;
  nonce service-generated via `secrets.token_hex`, independent per new
  authorization, never regenerated on replay.
- No `ExecutionClaim`, no `ExecutionAttempt`, no worker, no execution state
  transition, no `app.py` integration. `AUTHORIZED_FOR_EXECUTION` remains a
  derived condition, not stored state.

**Preserved invariant:** `ACCEPTED != EXECUTION AUTHORIZATION`. EA-3I.2 creates
durable, replay-safe, policy-bound execution authorization evidence and nowhere
beyond. EA-4 (claim/consumption) remains separately authorized.

Tests: 21 focused EA-3I.2 tests (happy HUMAN authorize, POLICY_SERVICE
REQUIRES_HUMAN, SYSTEM DENY, errors, acceptance substitution, constrained scope,
clock/expiry/nonce, replay idempotency, actor-substitution-after-terminal,
atomic rollback through issuance, static execution-boundary scan) plus 5
mutation teeth (acceptance bypass, scope widening, replay minting, expiry
bypass, actor-role bypass) — all PASS, byte-exact restoration.
