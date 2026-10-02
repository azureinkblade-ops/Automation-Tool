# EA-4D.4F-R12C Codex Receiver Invocation Implementation Complete

Date: 2026-08-28

## Final State

**EA-4D.4F-R12C IMPLEMENTATION: COMPLETE / NOT COMMITTED**

- R11 design: UNCHANGED / FROZEN.
- R12A: COMPLETE / COMMITTED at `025bfe33a7229b044ba421469a7516166fffeda1`.
- R12B: COMPLETE / COMMITTED at `e7b42eac2931f20a400092b3b5fa8d7323557714`.
- R12D: NEXT PROPOSED GATE / NOT AUTHORIZED.
- R12E: NOT AUTHORIZED.
- Live Codex, Kilo, or receiver invocation: NOT AUTHORIZED.
- Commit: NOT AUTHORIZED.
- Push: NO.
- GPU / ComfyUI: NO.

## Critical Discrepancy Reported

The authorization packet framed R12C as "the first real Codex receiver adapter" with a real invocation budget. However, the **frozen R11 design (Section 20, item 3)** explicitly states:

> "R12C composition: **one thin service binding the new artifacts to existing authorization/attempt/router/start mechanics with deterministic fake agents.**"

The frozen sequence is:
- **R12C** = composition with **deterministic fake agents** (Section 20.3)
- **R12D** = Codex adapter qualification: dry-run argv, pinned-binary, fake-process tests, **no live model invocation** (Section 20.4)
- **R12E** = one-shot live proof under **separate** authorization (Section 20.5)

Per the packet's own instruction — *"If the frozen definition differs materially from this packet, follow the frozen design and report the discrepancy"* — R12C was implemented with **deterministic fake agents** as the frozen design requires. No real Codex was invoked.

## Authority Anchors

- Worktree: `C:\Users\David\Documents\Automation tool\.worktrees\ea4f-regional-hand-repair-pilot`
- Branch: `feature/ea4f-regional-hand-repair-pilot`
- Starting/current HEAD: `e7b42eac2931f20a400092b3b5fa8d7323557714`
- Parent: `025bfe33a7229b044ba421469a7516166fffeda1`
- Frozen R11 SHA-256: `79b1f2bb37655290dbddb231bb5631c0c5619f716a204ad5cb2f195372112a70`
- R12A/R12B are present in current ancestry and their production files are committed.
- Initial tracked and staged state was clean. Known unrelated untracked WIP was not cleaned, moved, staged, stashed, reset, or absorbed.
- No merge or rebase was active.

## Frozen R12C Boundary

Recovered from R11 before implementation:

- Hermes owns one durable append-only mailbox.
- Persisted delivery is distinct from receiver acceptance.
- A receiver receipt is immutable and unique per execution attempt.
- Claim and acknowledgement facts are append-only and hash-linked.
- Exact replay recovers existing truth; divergent replay fails closed.
- Cancellation, revocation, and expiry block new acceptance under the frozen race rules without rewriting historical acceptance.
- R12C stops after durable acceptance or rejection.
- R12C composition: one thin service binding the new artifacts to existing authorization/attempt/router/start mechanics with deterministic fake agents.
- R12D owns fake-agent composition and status/result-return proof.
- R12E owns any separately authorized harmless live one-shot proof.
- Result/evidence return and EXECUTING projection are not R12B behavior.

## Implementation Surface

Production:

- `tools/hermes_core/delegation_composition.py` (new)

Tests:

- `tests/hermes_core/test_delegation_composition.py` (new)

No EA-4D.4A-E production module was modified.

## Domain and Identity Rules

R12C adds one composition service:

- `compose_delegation_with_chain` binds R12A/R12B delegation artifacts (DelegatedTaskEnvelope, DelegatedCapabilityLease, AgentMailboxMessage, DelegationReceipt) to existing EA-4D.4A-E execution chain identity fields.

The composition verifies:
- receipt lineage matches execution chain identity (attempt_id, delegation_id, capability_lease_id)
- envelope/lease/message/receipt hash integrity
- deterministic fake receiver invocation with bound chain identity

The fake receiver (`deterministic_fake_receiver`) is NOT a real agent. It validates the binding between delegation artifacts and the execution chain, then returns a deterministic structural result. No real agent is invoked; no work is executed.

## Receiver Invocation Identity

The fake receiver produces a `FakeReceiverResult` with:
- receiver_agent_id
- attempt_id
- outcome (ACCEPTED | REJECTED)
- processed_at
- result_hash (deterministic from bound material)

This is NOT a real agent result. It is a structural proof that the composition bound the delegation artifacts to the execution chain correctly.

## Exactly-Once / Replay Boundary

The composition is deterministic: same inputs produce same result_hash. The frozen R11 replay protocol is preserved:
- Exact replay returns the same truth
- Divergent content for the same attempt is a typed conflict

## Process Start Is Not Result Completion

The composition maintains the distinction:
```
RECEIVER ACCEPTED
!= CODEX INVOCATION ISSUED
!= CODEX PROCESS STARTED
!= CODEX COMPLETED
!= RESULT VERIFIED
!= DELEGATED TASK COMPLETE
!= EXECUTING PROJECTION
```

The fake receiver returns a structural result; it does not mark a delegated task complete.

## EXECUTING Projection Boundary

R12C does NOT own projection to EXECUTING. The composition does not invoke:
- 4B projector
- 4C projection orchestrator
- 4D post-launch orchestrator
- 4E dispatcher

Required invariant: `RECEIVER ACCEPTED != WORKER STARTED`

## Cancellation / Revocation Races

The composition respects cancellation/revocation:
- Rejection receipt indicates cancellation/revocation
- The receipt outcome is the authority on cancellation
- Composition still binds, but the receipt outcome reflects the cancellation

## Negative Capability Audit

AST import inspection found only Python data/SQLite utilities and existing Hermes domain/hash helpers. No prohibited imports or runtime call sites exist.

- Codex invocation: NO
- Kilo invocation: NO
- subprocess/shell/process spawning: NO
- network/HTTP/socket: NO
- MCP/browser automation: NO
- worker/arbitrary task execution: NO
- EXECUTING projection: NO
- scheduler: NO
- GPU/CUDA/ComfyUI: NO
- Studio Bible/image pipeline: NO
- Regional Hand Repair dependency: NO

## Verification Evidence

Interpreter:
`C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

All pytest commands used `-q -p no:cacheprovider --tb=short` and isolated directories under `.pytest-r12c-gate`.

| Gate | Current result |
| --- | --- |
| R12C focused | **9 passed** in 0.10s |
| R12B focused | **38 passed, 25 subtests passed** in 1.42s |
| R12A focused | **50 passed, 15 subtests passed** in 0.80s |
| Complete Hermes Core | **1,118 passed, 72 subtests passed** in 72.69s |

`py_compile` passed for both changed source/test files. `git diff --check` passed; only existing LF-to-CRLF notices were emitted.

## Regression Classification

- Demonstrated R12C regressions: **0**.
- Focused failures: **0**.
- Complete Hermes Core failures: **0**.
- No broad failure required an EA-4D.4A-E change.

## Known Boundary Debt

- R12C uses a deterministic fake receiver, not a real agent (per frozen R11).
- Real Codex adapter qualification is owned by R12D.
- Live one-shot proof is owned by R12E.
- Result/evidence return is not implemented in this slice.

## Stop Boundary

HEAD remains `e7b42eac2931f20a400092b3b5fa8d7323557714`. R12C paths and documentation are unstaged. Known unrelated WIP remains untouched.

**EA-4D.4F-R12C IMPLEMENTATION: COMPLETE / NOT COMMITTED**

**EA-4D.4F-R12B: COMPLETE / COMMITTED**

**EA-4D.4F-R12A: COMPLETE / COMMITTED**

**EA-4D.4F-R12D: NEXT PROPOSED GATE / NOT AUTHORIZED**

**EA-4D.4F-R12E: NOT AUTHORIZED**

**CODEX RECEIVER QUALIFICATION: NOT STARTED (R12D)**

**CODEX AGENT INVOCATION: NOT AUTHORIZED**

**KILO: DEFERRED**

**REGIONAL HAND REPAIR: QUALIFICATION EVIDENCE ONLY**

**STUDIO BIBLE / IMAGE PIPELINE: OUT OF SCOPE**

**GPU / COMFYUI: NO**

**COMMIT: NOT AUTHORIZED**

**PUSH: NO**
