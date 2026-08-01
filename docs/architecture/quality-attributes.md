---
title: "Hermes Quality Attributes"
document_id: "ARCH-QUALITY"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Quality Attributes

## 1. Auditability

Every material decision must be reconstructable from:

- input artifacts;
- policies;
- model identities;
- reviewer reports;
- authorizations;
- state transitions;
- output artifacts.

## 2. Reproducibility

A review or validation should be reproducible from frozen inputs and recorded configuration.

## 3. Reliability

The system must:

- survive process restart;
- avoid partial state transitions;
- detect duplicate messages;
- preserve audit history;
- recover from projection failures.

## 4. Security

The system must enforce least authority and fail closed.

## 5. Maintainability

- modular boundaries;
- typed interfaces;
- versioned schemas;
- ADR-governed major changes;
- comprehensive tests.

## 6. Portability

Initial target is Windows, but paths and process handling should be normalized to support later Linux deployment.

## 7. Performance

Initial goals should favor correctness over throughput.

Track:

- deterministic validation duration;
- model review latency;
- context size;
- consensus duration;
- event backlog;
- projection delay.

## 8. Scalability

The architecture should scale from:

- one workstation;
- a few agents;
- local SQLite;
- synchronous reviews;

to:

- multiple workers;
- queued events;
- remote stores;
- distributed model serving.

No distributed complexity should be introduced before local correctness.

## 9. Explainability

Every disposition must include:

- governing rule;
- evidence identity;
- finding summary;
- unresolved uncertainty;
- next permitted action.

## 10. Usability

Human review packets should surface:

- blockers;
- high-risk findings;
- changes since last accepted state;
- disagreements;
- exact actions requiring human judgment.

## 11. Privacy

Private knowledge must remain local by default and be minimized in model context.

## 12. Testability

Every component must support deterministic substitutes for external systems.

## 13. Measurable acceptance targets

Examples:

- zero unauthorized state transitions;
- zero reviewer tool access;
- 100% audit-event creation for governed transitions;
- 100% evidence-root match across consensus-eligible reports;
- explicit terminal outcome for every review chain.
