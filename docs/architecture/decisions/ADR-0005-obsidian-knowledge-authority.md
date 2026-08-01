# ADR-0005 Obsidian Is the Canonical Long-Term Knowledge System

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Durable knowledge and memory
* **Related:** ADR-0001, ADR-0012

## Context

Hermes requires durable knowledge covering:

* architecture;
* rationale;
* governance explanations;
* operating procedures;
* project history;
* research;
* fiction canon;
* personas;
* postmortems;
* accepted lessons.

This material is primarily human-readable, relational, and long-lived. It is not equivalent to runtime workflow state.

## Decision

Obsidian will serve as the canonical long-term semantic knowledge system.

Obsidian owns:

* architecture explanations;
* accepted ADR mirrors;
* research notes;
* runbooks;
* project documentation;
* human-readable decision history;
* fiction canon and continuity;
* accepted operational lessons;
* reusable knowledge.

Obsidian will not be authoritative for:

* active gate state;
* current authorization;
* consensus calculation;
* execution locks;
* runtime secrets;
* task queues;
* package manifests;
* cryptographic acceptance.

Hermes may retrieve knowledge from Obsidian, but must not treat arbitrary notes as governing policy.

## Document classification

Every machine-retrievable note should declare a status:

```yaml
document_status: canonical | draft | archived
authority: approved_reference | non_authoritative
project: hermes
schema_version: 1
```

Draft notes may inform exploration but may not override accepted policies or repository evidence.

## Consequences

### Positive

* Knowledge remains readable and editable by the user.
* Links and backlinks support long-term reasoning.
* Existing Azure Inkblade knowledge can remain in one durable vault.
* Models can retrieve relevant context without owning the knowledge store.

### Negative

* Retrieval permissions and filtering are required.
* Notes can become stale.
* Canonical and draft content must be clearly separated.
* Obsidian cannot enforce runtime security.

## Synchronization

The tracked repository remains authoritative for executable policies and ADRs.

Accepted ADRs may be mirrored to:

```text
Obsidian Vault/Architecture/Hermes/Decisions/
```

The mirror should retain:

* repository path;
* source commit;
* content SHA-256;
* synchronization timestamp.
