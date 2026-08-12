# ADR-0012 Durable Memory Requires Controlled Promotion

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Learning and long-term memory
* **Related:** ADR-0002, ADR-0005

## Context

Agents will produce observations, summaries, proposed lessons, technical findings, and project knowledge.

Automatically writing every model conclusion into Obsidian would create duplicated, contradictory, or false long-term memory. At the same time, requiring manual entry for every useful observation would make the system impractical.

## Decision

Models may propose memory, but they may not directly promote their conclusions into canonical long-term knowledge.

The memory workflow is:

```text
Observation
    ↓
Memory proposal
    ↓
Source and duplication checks
    ↓
Conflict detection
    ↓
Reviewer assessment
    ↓
Human or policy acceptance
    ↓
Canonical Obsidian update
    ↓
Anytype projection update
```

## Memory proposal fields

A memory proposal must include:

* proposed claim;
* project;
* destination;
* source artifact references;
* source hashes;
* confidence;
* known conflicts;
* document classification;
* proposing agent;
* timestamp.

## Promotion classes

### Automatic promotion eligible

Only low-risk, deterministic facts may become eligible after policy validation, such as:

* test count;
* exact package version;
* accepted artifact hash;
* completed task identifier.

### Review required

Semantic conclusions require model review or human confirmation:

* architectural lessons;
* root-cause conclusions;
* workflow recommendations;
* canon interpretation;
* governance interpretation.

### Human required

The following require explicit human review:

* security conclusions;
* rights or licensing claims;
* production policy changes;
* personal information;
* irreversible decisions;
* material novel-canon changes.

## Consequences

### Positive

* The system can learn without silently treating model output as truth.
* Canonical knowledge remains traceable.
* Conflicting memories can be surfaced before promotion.

### Negative

* Memory ingestion becomes slower.
* Proposal queues require maintenance.
* Deduplication and conflict detection must be implemented.
