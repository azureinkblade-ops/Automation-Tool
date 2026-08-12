---
title: "Hermes Event Model"
document_id: "ARCH-EVENTS"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Event Model

## 1. Event principles

Events are:

- immutable;
- versioned;
- uniquely identified;
- correlated to a workflow;
- idempotent where applicable;
- append-only after acceptance.

## 2. Base envelope

```yaml
schema_version: "1.0"
event_id: "evt-uuid"
event_type: "review.completed"
occurred_at: "2026-07-31T00:00:00Z"
workflow_id: "wf-uuid"
task_id: "task-uuid"
correlation_id: "corr-uuid"
causation_id: "evt-parent"
sender:
  component: "reviewer-orchestrator"
  identity: "reviewer-a"
scope:
  project_id: "stage2-v2"
  gate_id: "gate3b"
payload: {}
integrity:
  payload_sha256: "<digest>"
```

## 3. Core event families

### Task events

- `task.requested`
- `task.validated`
- `task.blocked`
- `task.completed`

### Evidence events

- `evidence.discovered`
- `evidence.validated`
- `evidence.frozen`
- `evidence.invalidated`

### Review events

- `review.requested`
- `review.started`
- `review.completed`
- `review.rejected`
- `review.timed_out`

### Consensus events

- `consensus.started`
- `consensus.accepted`
- `consensus.escalated`
- `consensus.blocked`
- `consensus.inconclusive`

### Authorization events

- `authorization.requested`
- `authorization.issued`
- `authorization.rejected`
- `authorization.expired`
- `authorization.revoked`

### Execution events

- `execution.started`
- `execution.command_recorded`
- `execution.scope_violation`
- `execution.completed`
- `execution.failed`

### Memory events

- `memory.proposed`
- `memory.conflict_detected`
- `memory.approved`
- `memory.promoted`
- `memory.rejected`

## 4. Delivery semantics

Initial implementation should use at-least-once delivery with idempotent consumers.

Every mutating handler must store an idempotency key.

## 5. Retry policy

Retry only transient failures.

Do not retry:

- schema violations;
- authorization failures;
- scope violations;
- deterministic policy failures.

## 6. Loop prevention

Messages include:

```yaml
routing:
  hop_count: 2
  maximum_hops: 5
  visited_components:
    - librechat
    - hermes
```

Hermes rejects:

- exceeded hop limits;
- repeated prohibited routes;
- duplicate causation chains;
- recursive execution requests.

## 7. Schema evolution

- additive optional fields may remain within a minor version;
- breaking changes require a new major schema version;
- consumers must reject unsupported major versions;
- raw payloads must be retained for audit.
