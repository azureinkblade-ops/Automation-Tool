# ADR-0004 Gate Acceptance and Execution Authorization Are Separate

* **Status:** ACCEPTED
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Governance transitions
* **Related:** ADR-0001, ADR-0003

## Context

A successful review establishes that an evidence package satisfies a policy. It does not necessarily establish that the next operational action should begin immediately.

Combining acceptance and execution would allow a review result to trigger installs, modifications, inference, fixture execution, deployment, or publication without a distinct human or policy authorization.

## Decision

Gate acceptance and execution authorization will be separate artifacts and separate state transitions.

### Acceptance means

The identified evidence package satisfies the identified review and consensus policy.

### Execution authorization means

A specific operation may be performed within a defined scope, time, repository, path set, and tool boundary.

Acceptance must not automatically trigger execution.

## Required execution authorization fields

An execution authorization must include:

* task identifier;
* authorized phase;
* parent acceptance hash;
* allowed operations;
* prohibited operations;
* permitted read paths;
* permitted write paths;
* network policy;
* fixture policy;
* expiration or bounded lifetime;
* issuing authority;
* authorization SHA-256.

## Consequences

### Positive

* Review cannot accidentally trigger operational changes.
* Scope can be narrowly defined for each execution.
* Accepted evidence remains reusable without granting indefinite permission.
* Human control is preserved for high-impact actions.

### Negative

* The workflow requires an additional transition.
* Operators must understand the difference between accepted and authorized.
* More artifacts must be tracked.

## State flow

```text
EVIDENCE_FROZEN
      ↓
UNDER_REVIEW
      ↓
ACCEPTED
      ↓
AWAITING_EXECUTION_AUTHORIZATION
      ↓
AUTHORIZED_FOR_EXECUTION
      ↓
EXECUTING
      ↓
EXECUTION_VERIFIED
```
