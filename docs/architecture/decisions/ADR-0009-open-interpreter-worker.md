# ADR-0009 Open Interpreter Is a Restricted Execution Worker

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Local command and code execution
* **Related:** ADR-0001, ADR-0004, ADR-0011

## Context

Some workflows require filesystem inspection, tests, hashing, validation scripts, code modification, and controlled terminal execution.

A reasoning model should not receive unrestricted machine authority. Execution must remain bounded by an explicit authorization envelope.

## Decision

Open Interpreter may be integrated as a restricted execution worker.

It receives tasks only after Hermes validates an execution authorization.

It may perform only operations listed in a machine-readable execution envelope.

The execution worker may not:

* define its own scope;
* widen path access;
* install unapproved dependencies;
* access the network when prohibited;
* modify governance artifacts;
* authorize its own results;
* access frozen fixtures outside scope;
* push, deploy, publish, or activate without explicit authorization;
* recursively invoke governance or reviewer agents.

## Execution envelope

Every task must define:

* task ID;
* authorization hash;
* parent acceptance hash;
* allowed commands or operation classes;
* read-path allowlist;
* write-path allowlist;
* network policy;
* environment policy;
* timeout;
* expected outputs;
* stop conditions;
* prohibited operations.

## Result requirements

The worker returns:

* status;
* exit code;
* command ledger;
* input hashes;
* output paths and hashes;
* environment identity;
* detected scope violations;
* errors;
* no approval claim.

## Consequences

### Positive

* Execution becomes auditable and separable from reasoning.
* The same worker can support testing, evidence generation, and authorized repairs.
* Reviewers can inspect an immutable execution record.

### Negative

* Natural-language restrictions are insufficient by themselves.
* A wrapper or sandbox must enforce paths and commands.
* Windows, Bash, PowerShell, and Python environments require careful normalization.
