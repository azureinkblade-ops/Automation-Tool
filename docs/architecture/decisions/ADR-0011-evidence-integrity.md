# ADR-0011 Evidence Is Immutable, Hash-Bound, and Auditable

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Evidence and audit
* **Related:** ADR-0001, ADR-0003, ADR-0004

## Context

Gate decisions depend on manifests, logs, test reports, model identities, environment records, reviewer reports, and authorization artifacts.

Narrative claims such as “verified,” “frozen,” or “complete” are insufficient without evidence identity and reproducibility.

## Decision

Every governance-relevant evidence package will be immutable after freezing and identified by a cryptographic root hash.

Evidence records must include:

* schema version;
* task and gate identity;
* artifact path;
* artifact SHA-256;
* generation tool;
* tool version;
* creation timestamp;
* input identities;
* status;
* relevant environment identity.

Downstream artifacts must reference their parent evidence hashes.

## Mutation policy

When a frozen artifact changes:

* its prior identity remains in history;
* a new artifact hash is generated;
* dependent review reports become stale;
* consensus must be recomputed;
* prior acceptance does not transfer automatically.

## Audit ledger

Hermes will maintain an append-only event ledger containing:

* state transition;
* actor;
* previous state;
* next state;
* governing rule;
* input hashes;
* output hashes;
* authorization hash;
* result;
* timestamp.

## Consequences

### Positive

* Decisions can be independently reconstructed.
* Evidence tampering is detectable.
* Reviewer reports remain bound to exact inputs.
* Historical decisions remain explainable.

### Negative

* Storage usage increases.
* Regeneration and amendment procedures are necessary.
* Hashing alone does not prove truth; deterministic and semantic validation remain required.
