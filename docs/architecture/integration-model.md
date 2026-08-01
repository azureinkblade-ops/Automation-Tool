---
title: "Hermes Integration Model"
document_id: "ARCH-INTEGRATIONS"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Integration Model

## 1. Integration rule

External systems communicate through adapters and versioned contracts. No integration receives raw database write access.

## 2. LibreChat

### Role

- user interface;
- conversation management;
- agent presentation;
- report display;
- explicit user input collection.

### Boundary

LibreChat messages are requests. Hermes validates and records authority.

## 3. Ollama

### Role

- local model serving.

### Adapter responsibilities

- map registered model ID to Ollama tag;
- verify availability;
- enforce context and generation settings;
- capture model identity;
- reject unqualified tags;
- record latency and failures.

## 4. Obsidian

### Role

- canonical durable knowledge.

### Adapter responsibilities

- scoped search;
- metadata validation;
- content snapshot;
- hash generation;
- accepted memory write;
- link and provenance maintenance.

## 5. Anytype

### Role

- structured operational projection.

### Adapter responsibilities

- map Hermes entities to Anytype objects;
- update projection status;
- record synchronization receipts;
- accept only permitted reverse annotations;
- mark stale projections.

## 6. Open Interpreter

### Role

- restricted execution worker.

### Adapter responsibilities

- submit validated envelope;
- enforce wrapper controls;
- capture command ledger;
- collect output artifacts;
- report violations.

## 7. OpenJarvis

Deferred until:

- Hermes event schemas are stable;
- single-worker execution is proven;
- duplicate orchestration risk is assessed.

If introduced, it may route work but may not own governance or consensus.

## 8. Integration health

Each adapter exposes:

- connection status;
- version;
- last successful operation;
- permission scope;
- error summary;
- qualification status.

## 9. Failure isolation

- LibreChat outage: Hermes remains operable through CLI/API.
- Anytype outage: projections become stale, governance continues.
- Obsidian outage: tasks requiring durable knowledge pause or use approved snapshots.
- Ollama outage: reviewer task becomes inconclusive.
- Open Interpreter outage: execution does not begin or safely stops.

## 10. Data contracts

Every integration payload should include:

- schema version;
- sender and recipient;
- task and correlation ID;
- data classification;
- payload hash;
- acknowledgment or receipt.
