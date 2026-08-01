# ADR-0006 Anytype Is a Structured Operational Projection

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Dashboards and structured operational knowledge
* **Related:** ADR-0001, ADR-0005

## Context

Obsidian is well suited to long-form knowledge but less suited to typed operational dashboards showing projects, gates, agents, models, findings, reviews, tasks, and relationships.

Anytype provides structured objects, properties, relations, collections, and graph views.

## Decision

Anytype will serve as a structured operational projection of Hermes and the Azure Inkblade Studio.

Anytype may display:

* projects;
* agents;
* models;
* gates;
* review results;
* findings;
* tasks;
* incidents;
* decisions;
* publishing status;
* chapter status;
* experiment summaries.

Anytype is not authoritative for:

* gate acceptance;
* authorization;
* evidence hashes;
* consensus outcomes;
* security policies;
* execution state.

Hermes is the source of projected operational state.

## Synchronization direction

The default synchronization direction is:

```text
Hermes → Anytype
```

Limited reverse fields may be accepted, subject to Hermes validation:

* human notes;
* priority;
* assignment request;
* acknowledgment;
* display grouping.

A user changing an Anytype status must not directly change authoritative Hermes state.

## Consequences

### Positive

* The user receives a visual operational control room.
* Relationships among projects, agents, models, reviews, and findings become navigable.
* Obsidian is not overloaded with task-management responsibilities.

### Negative

* A synchronization adapter is required.
* Duplicate projections may become stale.
* Source-of-truth labels must remain visible.
* Bidirectional synchronization must be tightly constrained.
