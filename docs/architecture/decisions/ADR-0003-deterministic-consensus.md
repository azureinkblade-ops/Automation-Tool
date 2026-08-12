# ADR-0003 Acceptance Is Calculated by Deterministic Consensus

* **Status:** ACCEPTED
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Multi-model review
* **Related:** ADR-0001, ADR-0002

## Context

Multiple independent model reviews can reduce reliance on a single model. However, majority voting over unstructured conclusions is insufficient.

Models may agree on a top-level recommendation while disagreeing about material findings, severity, evidence, or policy interpretation. A model must not decide whether model agreement is sufficient.

## Decision

A deterministic Hermes consensus engine will evaluate validated review reports against a frozen consensus policy.

The consensus engine, not a model, determines whether the reports satisfy the acceptance criteria.

Initial policy:

* three required independent review reports;
* all reports bound to the same evidence root;
* all reports bound to the same governance policy and review contract;
* deterministic checks must pass;
* no unresolved critical findings;
* no unresolved high findings;
* no material disagreement;
* all reports must be schema-valid;
* unanimous acceptable recommendations are required initially.

A majority-vote policy may be considered only after reviewer reliability has been measured.

## Material agreement

Consensus must evaluate more than the top-level recommendation.

Reports must be normalized by:

* rule identifier;
* category;
* affected artifact or subject;
* finding claim;
* severity;
* blocking status;
* evidence pointer.

Material disagreement causes escalation even when all reviewers recommend acceptance.

## Terminal outcomes

The consensus engine may produce:

* `ACCEPTED`: The frozen policy is satisfied.
* `ESCALATED`: Human judgment or additional evidence is required.
* `BLOCKED`: An objective or material policy violation exists.
* `INCONCLUSIVE`: Sufficient valid review agreement could not be established.

## Consequences

### Positive

* Acceptance is reproducible.
* Model authority remains constrained.
* Consensus decisions are auditable.
* Disagreement is visible instead of hidden behind voting.

### Negative

* Finding normalization is technically complex.
* Conservative consensus may cause frequent escalation initially.
* Model reports must follow strict schemas.

## Implementation requirements

The consensus engine must:

1. Verify report signatures or hashes.
2. Verify evidence-root identity.
3. Reject malformed reports.
4. Reject reports from unregistered reviewers.
5. Normalize findings.
6. compare severity and disposition;
7. record every policy evaluation;
8. generate an acceptance or disposition artifact;
9. never execute the next phase automatically.
