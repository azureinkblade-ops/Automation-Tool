---
title: "Hermes Architecture Roadmap"
document_id: "ARCH-ROADMAP"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Architecture Roadmap

## Guiding rule

Each phase must leave a testable, independently useful capability. Later phases must not be required to prove earlier authority boundaries.

## Phase 0: Architecture foundation

### Deliverables

- architecture handbook;
- accepted ADR-0001 through ADR-0004;
- terminology and authority model;
- initial schemas;
- implementation repository layout.

### Exit criteria

- authority boundaries reviewed;
- acceptance and authorization distinguished;
- reviewer authority documented;
- negative control cases defined.

## Phase 1: Deterministic Hermes core

### Capabilities

- state machine;
- policy loading;
- event ledger;
- artifact registry;
- authorization validation;
- schema registry;
- CLI or minimal API.

### Exit criteria

- invalid transitions are rejected;
- state changes are idempotent;
- audit records are append-only;
- restart and recovery tests pass.

## Phase 2: Evidence package system

### Capabilities

- artifact inventory;
- SHA-256 calculation;
- evidence-root generation;
- immutable freeze operation;
- stale-dependency detection.

### Exit criteria

- any artifact mutation invalidates downstream review eligibility;
- evidence can be reconstructed and verified independently.

## Phase 3: Reviewer framework

### Capabilities

- reviewer registry;
- Ollama adapter;
- review contract;
- strict report schema;
- read-only evidence snapshots;
- report validation.

### Exit criteria

- reviewers cannot access execution tools;
- invalid reports are rejected;
- all reports bind to the same evidence root.

## Phase 4: Deterministic consensus

### Capabilities

- finding normalization;
- disagreement detection;
- terminal dispositions;
- acceptance artifact generation.

### Exit criteria

- unanimous clean review can produce acceptance;
- material disagreement escalates;
- deterministic failure blocks;
- acceptance never triggers execution.

## Phase 5: Memory gateway

### Capabilities

- scoped Obsidian retrieval;
- canonical/draft classification;
- memory proposal queue;
- conflict and duplication checks;
- controlled promotion.

### Exit criteria

- agents cannot write directly to canonical memory;
- retrieval packages are scoped and hashable.

## Phase 6: Anytype projection

### Capabilities

- project, gate, review, finding, model, and decision objects;
- one-way Hermes projection;
- limited validated reverse annotations.

### Exit criteria

- Anytype changes cannot mutate authoritative state;
- stale projections are visibly marked.

## Phase 7: LibreChat integration

### Capabilities

- human-agent interface;
- registered agent selection;
- Hermes request submission;
- report and state presentation.

### Exit criteria

- chat messages cannot bypass authorization;
- user confirmations are recorded through Hermes.

## Phase 8: Restricted execution

### Capabilities

- execution-envelope validation;
- Open Interpreter worker;
- command and path enforcement;
- command ledger;
- result evidence freezing.

### Exit criteria

- prohibited paths and commands are blocked;
- network restrictions are enforced;
- worker cannot modify governance;
- execution output cannot self-approve.

## Phase 9: Multi-agent workflows

### Capabilities

- event-driven routing;
- planner, reviewer, coder, verifier roles;
- loop prevention;
- bounded handoffs.

### Exit criteria

- hop limits and idempotency work;
- role authority remains isolated;
- complete workflow is auditable.

## Phase 10: Calibration and hardening

### Capabilities

- reviewer false-clear metrics;
- model change qualification;
- threat-model testing;
- disaster recovery;
- performance optimization.

## Deferred capabilities

- OpenJarvis integration;
- distributed workers;
- remote execution;
- majority-vote consensus;
- automatic production deployment;
- cross-device Anytype writeback.
