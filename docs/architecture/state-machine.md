---
title: "Hermes Governance State Machine"
document_id: "ARCH-STATE-MACHINE"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Governance State Machine

## Purpose

This document defines the first deterministic task-state model for the Hermes agent-to-agent pipeline.

It implements the boundary established by ADR-0001 through ADR-0004:

- Hermes owns governance state.
- Reviewer models are review-only.
- Acceptance is calculated by deterministic consensus.
- Execution authorization is separate from acceptance.

## States

| State | Meaning |
|---|---|
| `DRAFT` | Task exists but is not ready for review. |
| `READY_FOR_REVIEW` | Scope and evidence requirements are complete enough to begin review. |
| `UNDER_REVIEW` | One or more reviewers are evaluating a frozen evidence package. |
| `CONSENSUS_CALCULATED` | Review reports have been normalized and the consensus policy has run. |
| `ACCEPTED` | Consensus determined the evidence satisfies the policy. This does not authorize execution. |
| `REJECTED` | Consensus determined the evidence does not satisfy the policy. |
| `INCONCLUSIVE` | Consensus could not determine an accepted or rejected result. |
| `AWAITING_EXECUTION_AUTHORIZATION` | Accepted work is waiting for a separate authorization artifact. |
| `AUTHORIZED` | A valid authorization artifact exists for a bounded operation. |
| `EXECUTING` | An executor is performing the authorized operation. |
| `VALIDATION_PENDING` | Execution completed and output validation is required. |
| `VALIDATED` | Execution output passed validation. |
| `FAILED` | Execution or validation failed. |
| `CLOSED` | The task is complete, abandoned, or superseded. |

## Allowed transitions

| From | To | Required artifact or condition |
|---|---|---|
| `DRAFT` | `READY_FOR_REVIEW` | Task scope and evidence requirements pass schema validation. |
| `READY_FOR_REVIEW` | `UNDER_REVIEW` | Frozen evidence package exists. |
| `UNDER_REVIEW` | `CONSENSUS_CALCULATED` | Required review reports are complete or timed out by policy. |
| `CONSENSUS_CALCULATED` | `ACCEPTED` | Consensus result is `ACCEPTED`. |
| `CONSENSUS_CALCULATED` | `REJECTED` | Consensus result is `REJECTED`. |
| `CONSENSUS_CALCULATED` | `INCONCLUSIVE` | Consensus result is `INCONCLUSIVE`, `ESCALATED`, or `BLOCKED`. |
| `ACCEPTED` | `AWAITING_EXECUTION_AUTHORIZATION` | Acceptance artifact exists and references the evidence package. |
| `AWAITING_EXECUTION_AUTHORIZATION` | `AUTHORIZED` | Valid authorization artifact exists and references the parent acceptance hash. |
| `AUTHORIZED` | `EXECUTING` | Executor identity and requested operation match the authorization envelope. |
| `EXECUTING` | `VALIDATION_PENDING` | Execution finishes without scope violation. |
| `EXECUTING` | `FAILED` | Execution fails, is cancelled, or violates scope. |
| `VALIDATION_PENDING` | `VALIDATED` | Validation passes against the accepted evidence and authorized scope. |
| `VALIDATION_PENDING` | `FAILED` | Validation fails. |
| `REJECTED` | `CLOSED` | Operator or policy closes the rejected task. |
| `INCONCLUSIVE` | `CLOSED` | Operator or policy closes the inconclusive task. |
| `VALIDATED` | `CLOSED` | Final audit record is written. |
| `FAILED` | `CLOSED` | Failure record is written or retry task is opened. |

## Prohibited transitions

These transitions must be rejected by the runtime validator:

| From | To | Reason |
|---|---|---|
| `ACCEPTED` | `AUTHORIZED` | Missing separate authorization wait state and artifact validation. |
| `ACCEPTED` | `EXECUTING` | Acceptance is not execution permission. |
| `CONSENSUS_CALCULATED` | `AUTHORIZED` | Consensus cannot authorize execution. |
| `UNDER_REVIEW` | `AUTHORIZED` | Review reports cannot authorize execution. |
| `READY_FOR_REVIEW` | `EXECUTING` | Evidence has not been accepted or authorized. |
| `DRAFT` | `EXECUTING` | Draft tasks have no execution authority. |
| `EXECUTING` | `ACCEPTED` | Execution output cannot create acceptance. |
| `VALIDATED` | `AUTHORIZED` | Completed validation does not grant another execution. |

## Transition validation rules

1. Only Hermes may write authoritative task state.
2. Every transition must produce an immutable event.
3. Every transition must reference its parent event or artifact.
4. `ACCEPTED` requires a valid `hermes.acceptance` object.
5. `AUTHORIZED` requires a valid `hermes.authorization` object.
6. `authorization.parent_acceptance_sha256` must match the referenced acceptance artifact.
7. `EXECUTING` requires an unexpired authorization object.
8. An executor may only use operations, paths, tools, and network access listed in the authorization object.
9. Reviewer models may never emit state changes directly.
10. Any missing, expired, ambiguous, or mismatched artifact results in transition rejection.

## Minimal event sequence

```text
task.requested
task.validated
evidence.frozen
review.requested
review.completed
consensus.started
consensus.accepted
acceptance.recorded
authorization.requested
authorization.issued
execution.started
execution.completed
validation.completed
task.closed
```

## Implementation note

The first implementation should keep the transition table deterministic and data-driven. The validator should reject unknown states, unknown transitions, missing parent artifacts, and expired authorization artifacts before any worker is invoked.
