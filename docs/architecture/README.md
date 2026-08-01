---
title: "Hermes Architecture Handbook"
document_id: "ARCH-README"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Architecture Handbook

## Purpose

This handbook defines the architecture, authority boundaries, operating principles, information flows, and implementation direction for the Hermes agent platform.

Hermes is designed as a local-first, evidence-bound orchestration and governance system for multiple models, tools, knowledge systems, and execution workers. The architecture separates reasoning, review, acceptance, authorization, execution, memory, and user interaction so that no probabilistic model can silently become an execution or governance authority.

## Intended audience

This handbook is intended for:

- the system owner;
- implementation agents;
- reviewer models;
- security reviewers;
- maintainers;
- future contributors;
- operators investigating incidents or disputed state transitions.

## Documentation map

| Document | Purpose |
|---|---|
| [system-context.md](system-context.md) | System boundary, actors, external systems, trust boundaries, and source-of-truth hierarchy |
| [principles.md](principles.md) | Architectural principles that constrain design and implementation |
| [authority-model.md](authority-model.md) | Who may decide, review, authorize, execute, or write |
| [state-machine.md](state-machine.md) | Deterministic governance states, allowed transitions, and prohibited shortcuts |
| [hermes-core-validator.md](hermes-core-validator.md) | Executable schema and state-transition guard for the first governance core |
| [hermes-ledger-registry.md](hermes-ledger-registry.md) | Local append-only ledger and artifact registry for auditable governance state |
| [hermes-transition-recorder.md](hermes-transition-recorder.md) | Validated transition recording and latest-state replay |
| [hermes-evidence-package-builder.md](hermes-evidence-package-builder.md) | Frozen evidence package creation and verification |
| [glossary.md](glossary.md) | Canonical terminology |
| [architecture-roadmap.md](architecture-roadmap.md) | Phased implementation sequence and exit criteria |
| [component-model.md](component-model.md) | Component responsibilities and interfaces |
| [data-flow.md](data-flow.md) | Request, evidence, review, memory, and execution flows |
| [event-model.md](event-model.md) | Versioned messages, routing, idempotency, and event handling |
| [security-model.md](security-model.md) | Trust zones, permissions, secrets, isolation, and audit controls |
| [memory-model.md](memory-model.md) | Conversation, operational, and durable knowledge memory |
| [review-model.md](review-model.md) | Deterministic validation, reviewer reports, and consensus |
| [execution-model.md](execution-model.md) | Execution envelopes and restricted workers |
| [integration-model.md](integration-model.md) | LibreChat, Ollama, Obsidian, Anytype, and Open Interpreter |
| [repository-layout.md](repository-layout.md) | Recommended source, schema, evidence, and documentation layout |
| [schemas/README.md](schemas/README.md) | Core governance object contracts for the agent-to-agent pipeline |
| [technology-stack.md](technology-stack.md) | Initial technology choices and replacement boundaries |
| [quality-attributes.md](quality-attributes.md) | Reliability, auditability, security, portability, and performance |
| [threat-model.md](threat-model.md) | Assets, threats, mitigations, and residual risks |
| [decisions/README.md](decisions/README.md) | ADR index and lifecycle rules |

## Document authority

The repository-tracked handbook is authoritative for architecture intent. It is not itself an execution authorization.

The authority hierarchy is:

1. active runtime governance and authorization artifacts;
2. Hermes operational state and append-only audit history;
3. repository-tracked policies, schemas, ADRs, and this handbook;
4. canonical Obsidian knowledge;
5. Anytype operational projections;
6. LibreChat conversations and transient agent context.

A lower layer may summarize a higher layer but may not override it.

## Document lifecycle

Documents begin as `proposed`. They become `accepted` only after review. Material changes to accepted architecture should be recorded through an ADR or an explicitly versioned amendment.

Permitted lifecycle values:

- `draft`
- `proposed`
- `accepted`
- `deprecated`
- `superseded`
- `rejected`
- `archived`

## Writing conventions

Normative terms have the following meaning:

- **MUST**: mandatory for conformance.
- **MUST NOT**: prohibited.
- **SHOULD**: recommended unless a documented exception exists.
- **MAY**: optional.
- **AUTHORITATIVE**: the controlling source for a decision or state.
- **PROJECTION**: a readable or visual representation that cannot independently change authoritative state.

## Architecture summary

```text
User
  |
  v
LibreChat
  |
  v
Hermes Governance Core
  |-- State and authorization
  |-- Event routing
  |-- Evidence registry
  |-- Reviewer orchestration
  |-- Deterministic consensus
  |-- Memory gateway
  |
  +--> Ollama reviewer and worker models
  +--> Obsidian durable knowledge
  +--> Anytype operational projection
  +--> Open Interpreter restricted execution worker
```

## Initial implementation constraint

Implementation begins with deterministic contracts and state handling. Model orchestration, user interfaces, and execution workers are integrated only after authority, evidence, and transition rules have executable tests.
