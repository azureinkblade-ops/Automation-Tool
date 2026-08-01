---
title: "Hermes Technology Stack"
document_id: "ARCH-STACK"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Technology Stack

## 1. Core language

Python is recommended initially because of:

- existing automation code;
- model and validation ecosystem;
- cross-platform support;
- rapid schema and CLI development.

Use a supported pinned Python version and isolated environments.

## 2. Package management

Use `uv` or another lockfile-capable workflow. Dependencies must be pinned and reproducible.

## 3. State store

Initial recommendation: SQLite with:

- WAL where appropriate;
- foreign keys enabled;
- migrations;
- transaction boundaries;
- backup tooling.

A later move to PostgreSQL should require an ADR.

## 4. Schema validation

Use JSON Schema for integration artifacts and Pydantic or equivalent typed validation internally.

## 5. API

FastAPI is a reasonable initial local API, but the governance core must not depend semantically on a particular web framework.

## 6. Local model runtime

Ollama is the initial runtime.

Initial roles:

- Qwen-family technical reviewer;
- DeepSeek-R1 distilled adversarial reviewer;
- Qwen coder implementation agent.

Exact tags and digests belong in the model registry, not this document.

## 7. User interface

LibreChat is the initial interaction layer.

## 8. Durable knowledge

Obsidian is the canonical semantic knowledge store.

## 9. Operational projection

Anytype is the structured dashboard and object graph.

## 10. Execution worker

Open Interpreter is the initial restricted worker, behind an independent envelope-enforcement wrapper.

## 11. Hashing

SHA-256 is the baseline artifact identity function.

## 12. Testing

Use:

- unit tests;
- schema contract tests;
- integration tests;
- negative authority tests;
- security boundary tests;
- recovery tests.

## 13. Observability

Use structured JSON logs, correlation IDs, and metrics for:

- transitions;
- reviewer latency;
- reviewer disagreement;
- execution failures;
- scope violations;
- projection lag.

## 14. Replacement policy

Every external technology must be accessed through an adapter. Replacement requires proving contract compatibility, migration, and evidence continuity.
