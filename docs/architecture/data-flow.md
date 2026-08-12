---
title: "Hermes Data Flow"
document_id: "ARCH-DATAFLOW"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Data Flow

## 1. Request intake

```text
User -> LibreChat -> Hermes API -> Request validation -> Task record
```

A request is not authorization. Hermes resolves:

- actor;
- requested operation;
- task identity;
- relevant project;
- required policy;
- current state.

## 2. Evidence review flow

```text
Artifacts
  -> deterministic validation
  -> evidence inventory
  -> evidence freeze
  -> independent reviewers
  -> report validation
  -> finding normalization
  -> deterministic consensus
  -> disposition artifact
```

## 3. Execution flow

```text
Accepted evidence
  -> explicit execution authorization
  -> envelope validation
  -> restricted worker
  -> command ledger
  -> result artifacts
  -> freeze
  -> verification review
```

## 4. Memory retrieval flow

```text
Agent request
  -> authority and project scope
  -> Obsidian metadata search
  -> canonical/draft filtering
  -> relevance selection
  -> immutable retrieval snapshot
  -> agent context
```

## 5. Memory promotion flow

```text
Observation
  -> proposal
  -> source validation
  -> duplicate/conflict check
  -> review
  -> human or policy decision
  -> Obsidian write
  -> Anytype projection
  -> audit event
```

## 6. Operational projection flow

```text
Hermes state change
  -> projection event
  -> Anytype adapter
  -> object update
  -> projection receipt
```

Anytype failure does not roll back authoritative Hermes state. It creates a stale-projection alert.

## 7. Sequence: multi-model review

```text
Hermes          Reviewer A       Reviewer B       Reviewer C       Consensus
  |                 |                |                |                |
  |--snapshot A---->|                |                |                |
  |-----------------snapshot B----->|                |                |
  |----------------------------------snapshot C----->|                |
  |<--report A------|                |                |                |
  |<----------------report B--------|                |                |
  |<---------------------------------report C--------|                |
  |------------------------------------------------reports----------->|
  |<-----------------------------------------------disposition--------|
```

## 8. Data minimization

Every flow must minimize transferred data:

- project-scoped;
- role-scoped;
- sensitivity-filtered;
- time-bounded;
- limited to relevant artifacts.

## 9. Error paths

- Missing evidence: `BLOCKED` or `ESCALATED`.
- Reviewer timeout: `INCONCLUSIVE`.
- Report schema failure: report excluded; minimum-report policy reevaluated.
- Scope violation: worker stopped and task `BLOCKED`.
- Projection failure: retry and mark stale; do not alter source state.
