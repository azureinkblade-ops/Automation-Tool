# EA-4D.4F-R12B Delivery and Acceptance Implementation Complete

Date: 2026-08-28

## Final State

**EA-4D.4F-R12B IMPLEMENTATION: COMPLETE / NOT COMMITTED**

- R11 design: UNCHANGED / FROZEN.
- R12A: COMPLETE / COMMITTED at `025bfe33a7229b044ba421469a7516166fffeda1`.
- R12C: NEXT PROPOSED GATE / NOT AUTHORIZED.
- R12D-R12E: NOT AUTHORIZED.
- Live Codex, Kilo, or receiver invocation: NOT AUTHORIZED.
- Commit: NOT AUTHORIZED.
- Push: NO.
- GPU / ComfyUI: NO.

R12B implements only durable outbound delegation delivery, append-only mailbox
claim/acknowledgement state, and immutable receiver acceptance or rejection. It
does not invoke a receiver, execute delegated work, return terminal results, or
project work to `EXECUTING`.

## Authority Anchors

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting/current HEAD: `025bfe33a7229b044ba421469a7516166fffeda1`
- Parent: `67872e9d19d28294c9b8f8dc8ae28d3bec9ba5a3`
- Frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- R12A is present in current ancestry and its production files are committed.
- Initial tracked and staged state was clean. Known unrelated untracked WIP was
  not cleaned, moved, staged, stashed, reset, or absorbed.
- No merge or rebase was active.

## Frozen R12B Boundary

Recovered from R11 before implementation:

- Hermes owns one durable append-only mailbox.
- Persisted delivery is distinct from receiver acceptance.
- A receiver receipt is immutable and unique per execution attempt.
- Claim and acknowledgement facts are append-only and hash-linked.
- Exact replay recovers existing truth; divergent replay fails closed.
- Cancellation, revocation, and expiry block new acceptance under the frozen
  race rules without rewriting historical acceptance.
- R12B stops after durable acceptance or rejection.
- R12C owns fake-agent composition and status/result-return proof.
- R12D owns Codex adapter qualification.
- R12E owns any separately authorized harmless live one-shot proof.
- Result/evidence return and `EXECUTING` projection are not R12B behavior.

R11 described receipt/mailbox artifacts as frozen protocol objects, while the
committed R12A slice intentionally contained only delegation and lease objects.
R12B adds the missing delivery artifacts without changing committed R12A
identity semantics.

## Implementation Surface

Production:

- `tools/hermes_core/delegation_delivery.py` (new)
- `tools/hermes_core/sqlite_delegation_store.py` (extended)

Tests:

- `tests/hermes_core/test_delegation_delivery.py` (new)
- `tests/hermes_core/test_sqlite_delegation_delivery.py` (new)
- `tests/hermes_core/test_sqlite_delegation_store.py` (schema/integrity update)

No EA-4D.4A-E production module was modified.

## Domain and Identity Rules

R12B adds three immutable, hash-bound protocol artifacts:

- `AgentMailboxMessage`
- `MailboxDeliveryEvent`
- `DelegationReceipt`

Mailbox message identity derives from `mailbox_id` plus `idempotency_key`.
Canonical material binds sender, named receiver, delegation and attempt
lineage, schema, payload hash, ordering sequence, and creation time. Exact
logical replay recovers the existing message. Reuse of the same mailbox and
idempotency identity with changed material raises a typed conflict.

Delivery events are append-only and hash-linked per message. `CLAIMED` and
`ACKNOWLEDGED` events require the named receiver and active claim token. Exact
token replay is idempotent only when all event material is identical; changed
timestamps or expiry under the same token fail closed.

`DelegationReceipt` is distinct from delegation, task hash, lease,
authorization, execution attempt, launch attempt, runtime run, and future
result identity. It binds those lineage hashes plus receiver implementation and
version, source message, outcome, and decision timestamps. One attempt can have
exactly one immutable receipt.

## SQLite Schema and Migration

The existing R12A delegation database remains the single storage owner. Schema
version advances from **1 to 2** and adds:

- `agent_mailbox_messages`
- `agent_mailbox_delivery_events`
- `delegation_receipts`

The v1-to-v2 migration is explicit, atomic, non-destructive, and preserves
existing delegations, leases, cancellations, and revocations. Fresh databases
create the current schema directly. Current-schema reopen is stable; partial or
invalid migration state fails closed. Connections close explicitly for Windows.

Receipt persistence and its Hermes-directed `RECEIPT` mailbox message occur in
one transaction. Interrupted writes roll back instead of exposing partial truth.

## Delivery, Acceptance, and Race Semantics

Before delivery the store verifies delegation and lease integrity, named
receiver, lineage, bounded operation/capability, cancellation, revocation, and
expiry. Delivery grants no execution authority and creates no acceptance.

Acceptance requires the original durable `DELEGATION` message, an active claim
held by its named receiver, matching delegation/task/lease/authorization/
attempt/route/receiver lineage, and an unexpired claim. `ACCEPTED` also requires
that cancellation, revocation, and lease expiry have not become authoritative.

Rejection is a durable protocol decision with a frozen reason code and summary;
it is not an execution or launch failure. Exact receipt replay returns the same
truth. Divergent content or outcome for the same attempt is a typed conflict.
Accept-then-reject and reject-then-accept are forbidden immutable transitions.

Cancellation, revocation, or expiry before delivery blocks delivery. If one
becomes authoritative after delivery but before acceptance, new acceptance is
blocked. Historical acceptance is not rewritten by later authority facts.

## Recovery Evidence

Focused tests cover rollback during delivery and receipt creation, lost caller
responses followed by replay, repeated reads, receiver crash before receipt,
reopen after delivery/acceptance/rejection, replay/conflict after reopen, claim
expiry/redelivery, races, tamper, v1 migration, and malformed partial migration.

## Negative Capability Audit

AST import inspection found only Python data/SQLite utilities and existing
Hermes domain/hash helpers. No prohibited imports or runtime call sites exist.

- Codex invocation: NO
- Kilo invocation: NO
- subprocess/shell/process spawning: NO
- network/HTTP/socket: NO
- MCP/browser automation: NO
- worker/arbitrary task execution: NO
- `EXECUTING` projection: NO
- scheduler: NO
- GPU/CUDA/ComfyUI: NO
- Studio Bible/image pipeline: NO
- Regional Hand Repair dependency: NO

## Verification Evidence

Interpreter:
`C:\Users\David\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

All pytest commands used `-q -p no:cacheprovider --tb=line` and isolated
directories under `.pytest-r12b-tmp`.

| Gate | Current result |
| --- | --- |
| R12B focused | **38 passed, 25 subtests passed** in 1.17s |
| R12A focused | **50 passed, 15 subtests passed** in 0.76s |
| Combined R12A/R12B focused | **88 passed, 40 subtests passed** in 1.91s |
| EA-4D.4E | **19 passed** in 0.28s |
| EA-4D.4D | **11 passed** in 0.43s |
| EA-4D.4C | **11 passed** in 0.26s |
| EA-4D.4B | **25 passed** in 0.82s |
| EA-4D.4A | **28 passed** in 0.55s |
| Authority / attempt stores | **303 passed** in 35.64s |
| Worker routing | **85 passed** in 9.85s |
| Launch admission / coordinator | **33 passed** in 1.55s |
| Start result | **116 passed** in 2.51s |
| Start-store migration | **11 passed** in 0.27s |
| Complete Hermes Core | **1,109 passed, 72 subtests passed** in 78.39s |

`py_compile` passed for all five changed source/test files. `git diff --check`
passed; only existing LF-to-CRLF notices were emitted.

## Regression Classification

- Demonstrated R12B regressions: **0**.
- Focused failures: **0**.
- Complete Hermes Core failures: **0**.
- Claim/ack replay was tightened so the same token with changed event time or
  expiry is rejected as divergent material.
- No broad failure required an EA-4D.4A-E change.

## Known Boundary Debt

- R12B persists supplied launch/runtime lineage but deliberately does not
  compose it with lower Execution Authority stores; R12C owns that proof.
- Mailbox listing and explicit claim/ack exist, but no scheduler, automatic
  consumer, or live receiver loop exists.
- Result/evidence return is not implemented in this slice.
- `DEAD_LETTER` is supported by the artifact/schema, but R12B exposes no
  production transition method because the first delivery gate does not need it.

## Stop Boundary

HEAD remains `025bfe33a7229b044ba421469a7516166fffeda1`. R12B paths and
documentation are unstaged. Known unrelated WIP remains untouched.

**EA-4D.4F-R12B IMPLEMENTATION: COMPLETE / NOT COMMITTED**

**EA-4D.4F-R12A: COMPLETE / COMMITTED**

**EA-4D.4F-R12C: NEXT PROPOSED GATE / NOT AUTHORIZED**

**EA-4D.4F-R12D-R12E: NOT AUTHORIZED**

**CODEX AGENT INVOCATION: NOT AUTHORIZED**

**KILO: DEFERRED**

**REGIONAL HAND REPAIR: QUALIFICATION EVIDENCE ONLY**

**STUDIO BIBLE / IMAGE PIPELINE: OUT OF SCOPE**

**GPU / COMFYUI: NO**

**COMMIT: NOT AUTHORIZED**

**PUSH: NO**
