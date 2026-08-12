# ADR-0001 Hermes Is the Sole Governance Authority

* **Status:** ACCEPTED
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Hermes platform
* **Supersedes:** None

## Context

The planned system includes several components capable of reasoning, routing, retrieval, visualization, or execution:

* Hermes
* LibreChat
* Obsidian
* Anytype
* Ollama
* Reviewer models
* Open Interpreter
* Potentially OpenJarvis

Allowing multiple components to interpret permissions, approve transitions, or modify workflow state would create conflicting authorities. A model, user interface, automation framework, or knowledge application could incorrectly widen scope or declare a gate complete.

The system requires one component to own governance state and enforce transitions.

## Decision

Hermes will be the sole governance authority.

Hermes owns:

* workflow state;
* gate state;
* authorization validation;
* scope enforcement;
* consensus evaluation;
* acceptance generation;
* execution authorization validation;
* authoritative agent and model registrations;
* immutable event history;
* evidence identity binding;
* security boundary enforcement.

Other components may submit requests, reports, evidence, or user instructions, but they may not directly alter authoritative governance state.

No language model is a governance authority.

LibreChat, Obsidian, Anytype, Open Interpreter, Ollama, and OpenJarvis must interact with governance through versioned Hermes interfaces.

## Consequences

### Positive

* A single source of truth exists for workflow state.
* Authorization rules can be tested deterministically.
* Conflicting approvals are prevented.
* User interfaces and tools can be replaced without changing governance.
* Audit trails are easier to reconstruct.

### Negative

* Hermes becomes a critical system dependency.
* Hermes requires robust backup, migration, testing, and recovery procedures.
* Integrations must use explicit contracts instead of modifying state directly.

## Implementation requirements

Hermes must provide:

1. A persistent state store.
2. Versioned governance schemas.
3. A transition validator.
4. An append-only event ledger.
5. Authorization validation.
6. Evidence-hash validation.
7. Idempotent state transitions.
8. Clear terminal states such as:

   * `ACCEPTED`
   * `ESCALATED`
   * `BLOCKED`
   * `INCONCLUSIVE`
9. Interfaces for read-only projections into Obsidian and Anytype.
10. A rule preventing external components from directly editing authoritative state.

## Rejected alternatives

### LibreChat as governance authority

Rejected because LibreChat is primarily an interaction and agent-management surface.

### Obsidian or Anytype as governance authority

Rejected because user-editable documents and objects are not reliable transactional security boundaries.

### Model-decided governance

Rejected because model output is probabilistic and may contain unsupported or inconsistent conclusions.
