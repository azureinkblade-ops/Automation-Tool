---
title: "Hermes Component Model"
document_id: "ARCH-COMPONENTS"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Component Model

## 1. Governance Engine

### Responsibilities

- load policy;
- evaluate transition preconditions;
- enforce authority;
- produce dispositions;
- reject invalid actions.

### Interfaces

- `evaluate_transition`
- `validate_authorization`
- `record_decision`
- `get_current_state`

## 2. State Store

Stores authoritative workflow and task state.

Requirements:

- transactional writes;
- idempotency;
- migration support;
- backup and recovery;
- no direct external writes.

## 3. Audit Ledger

Append-only history of:

- requests;
- validations;
- transitions;
- authorizations;
- reviewer reports;
- execution results;
- memory promotions.

## 4. Evidence Registry

Tracks:

- artifact identity;
- package membership;
- root hash;
- freeze state;
- parent-child relationships;
- stale downstream artifacts.

## 5. Authorization Service

Validates:

- issuing authority;
- scope;
- parent acceptance;
- time bounds;
- path bounds;
- tool bounds;
- network policy;
- fixture policy.

## 6. Agent Registry

Each agent record contains:

- agent ID;
- role;
- authority class;
- model identity;
- prompt or contract version;
- allowed context;
- allowed tools;
- output schema;
- active status.

## 7. Model Registry

Each model record contains:

- provider;
- model and tag;
- digest or revision;
- quantization;
- context limit;
- role eligibility;
- qualification report;
- active/deprecated state.

## 8. Reviewer Orchestrator

Creates independent reviewer tasks and ensures:

- common evidence root;
- no reviewer-to-reviewer visibility;
- context limits;
- report collection;
- timeout handling.

## 9. Consensus Engine

Normalizes and evaluates reports without calling a model.

## 10. Event Router

Routes versioned messages while enforcing:

- sender identity;
- recipient permissions;
- hop count;
- deduplication;
- correlation;
- retry policy.

## 11. Memory Gateway

Provides:

- scoped retrieval;
- note classification;
- snapshot creation;
- memory proposals;
- controlled promotion.

## 12. Integration adapters

### LibreChat adapter

Converts user interactions into Hermes requests.

### Ollama adapter

Invokes qualified models.

### Obsidian adapter

Reads scoped knowledge and writes approved canonical updates.

### Anytype adapter

Projects structured operational data.

### Open Interpreter adapter

Submits execution envelopes and captures ledgers.

## 13. API

The API should expose narrow operations, not raw database access.

Initial namespaces:

- `/tasks`
- `/state`
- `/evidence`
- `/reviews`
- `/consensus`
- `/authorizations`
- `/events`
- `/memory`
- `/registry`
- `/projections`
