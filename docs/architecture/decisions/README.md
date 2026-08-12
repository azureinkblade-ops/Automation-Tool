---
title: "Hermes Architecture Decision Records"
document_id: "ADR-INDEX"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Architecture Decision Records

## Purpose

This directory contains authoritative records of durable architectural decisions.

## Lifecycle

- `proposed`
- `accepted`
- `rejected`
- `deprecated`
- `superseded`

Accepted ADRs should not be silently rewritten. Material changes require a new ADR or explicit amendment.

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](ADR-0001-hermes-governance-authority.md) | Hermes is the sole governance authority | Accepted |
| [ADR-0002](ADR-0002-reviewer-model-authority.md) | Reviewer models have review-only authority | Accepted |
| [ADR-0003](ADR-0003-deterministic-consensus.md) | Acceptance is calculated by deterministic consensus | Accepted |
| [ADR-0004](ADR-0004-acceptance-vs-execution.md) | Acceptance and execution authorization are separate | Accepted |
| [ADR-0005](ADR-0005-obsidian-knowledge-authority.md) | Obsidian is canonical durable knowledge | Proposed |
| [ADR-0006](ADR-0006-anytype-operational-projection.md) | Anytype is an operational projection | Proposed |
| [ADR-0007](ADR-0007-librechat-interaction-layer.md) | LibreChat is the interaction layer | Proposed |
| [ADR-0008](ADR-0008-ollama-local-runtime.md) | Ollama is the initial local model runtime | Proposed |
| [ADR-0009](ADR-0009-open-interpreter-worker.md) | Open Interpreter is a restricted worker | Proposed |
| [ADR-0010](ADR-0010-event-driven-communication.md) | A2A communication uses versioned events | Proposed |
| [ADR-0011](ADR-0011-evidence-integrity.md) | Evidence is immutable and hash-bound | Proposed |
| [ADR-0012](ADR-0012-controlled-memory-promotion.md) | Durable memory uses controlled promotion | Proposed |

## Acceptance order

Review ADR-0001 through ADR-0004 first. They establish authority, model limitations, consensus, and execution separation.
