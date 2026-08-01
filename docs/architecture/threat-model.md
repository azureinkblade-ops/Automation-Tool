---
title: "Hermes Threat Model"
document_id: "ARCH-THREATS"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Threat Model

## 1. Protected assets

- governance policy;
- authorization records;
- audit history;
- evidence packages;
- source repositories;
- Obsidian knowledge;
- Anytype operational data;
- model and agent registry;
- secrets;
- production credentials.

## 2. Threat actors

- malicious external content;
- compromised model;
- hallucinating or misconfigured model;
- compromised integration;
- accidental operator error;
- malicious dependency;
- unauthorized local process;
- recursive agent workflow.

## 3. Primary threats

### T1: Prompt injection in evidence

A file instructs the reviewer to ignore policy or execute commands.

Mitigation:

- reviewer has no tools;
- evidence treated as data;
- fixed review contract;
- output schema validation.

### T2: Reviewer authority escalation

A reviewer claims acceptance or generates a signature.

Mitigation:

- reviewer report has no state-changing interface;
- consensus ignores unsupported fields;
- governance authority separated.

### T3: Worker scope escape

A worker accesses unauthorized paths or network.

Mitigation:

- normalized path checks;
- OS isolation;
- allowlists;
- process monitoring;
- stop-on-violation.

### T4: Evidence tampering

Artifacts change after review.

Mitigation:

- evidence root;
- read-only freeze;
- downstream invalidation;
- re-review requirement.

### T5: Projection corruption

Anytype displays a false accepted state.

Mitigation:

- projection marked non-authoritative;
- state linked to acceptance hash;
- periodic reconciliation.

### T6: Knowledge poisoning

Draft or malicious notes enter canonical retrieval.

Mitigation:

- note classification;
- scoped retrieval;
- controlled promotion;
- conflict detection.

### T7: Recursive agent loop

Agents invoke one another indefinitely.

Mitigation:

- event routing;
- hop count;
- visited-component list;
- idempotency.

### T8: Model substitution

A different model or quantization is used under the same reviewer identity.

Mitigation:

- model digest and registry;
- qualification invalidation;
- report identity binding.

### T9: Authorization replay

An old authorization is reused.

Mitigation:

- expiration;
- nonce;
- parent-state binding;
- one-time or bounded-use policy;
- revocation.

### T10: Dependency supply-chain compromise

A package is modified or fetched unexpectedly.

Mitigation:

- lockfiles;
- offline wheelhouse for strict lanes;
- package hashes;
- isolated environments;
- provenance records.

## 4. Abuse cases

- user accidentally approves a broader scope than intended;
- model summarizes a partial log as complete;
- worker repairs evidence before review;
- reviewer sees another report and copies its conclusion;
- Anytype edit triggers unauthorized action;
- Obsidian draft overrides current repository evidence.

## 5. Residual risks

- models may agree incorrectly;
- local administrator access can bypass application controls;
- hashes prove identity, not truth;
- human confirmations may still be mistaken;
- complex Windows filesystem behavior may create path-edge cases.

## 6. Security review cadence

Review the threat model:

- before execution worker activation;
- after adding a new integration;
- after a material incident;
- after changing authority policy;
- before remote or distributed deployment.
