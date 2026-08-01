# ADR-0002 Reviewer Models Have Review-Only Authority

* **Status:** ACCEPTED
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Automated review system
* **Related:** ADR-0001, ADR-0003, ADR-0004

## Context

The volume of manifests, logs, qualification reports, evidence files, governance rules, and implementation changes exceeds what can reasonably be reviewed manually in full.

Model-assisted review is therefore required. However, allowing a reviewing model to approve its own conclusions, modify evidence, execute commands, or change gate state would collapse the separation between evaluation and authority.

## Decision

Reviewer models will have review-only authority.

A reviewer may:

* read an approved evidence package;
* compare evidence against governing policy;
* identify missing or contradictory information;
* classify findings;
* report uncertainty;
* cite exact artifacts and locations;
* recommend a disposition;
* produce a schema-valid review report.

A reviewer may not:

* approve a gate;
* issue execution authorization;
* alter governance state;
* modify evidence;
* repair a failure;
* install software;
* execute terminal commands;
* access frozen fixtures unless explicitly included in review scope;
* generate signatures;
* claim human approval;
* suppress deterministic validation failures.

Reviewer reports are advisory inputs to deterministic consensus.

## Required reviewer output

Every report must include:

* reviewer identity;
* exact model and revision;
* review-contract version;
* evidence-root SHA-256;
* governance-policy SHA-256;
* findings;
* evidence references;
* confidence;
* unresolved questions;
* recommended disposition;
* explicit confirmation that the reviewer has no approval authority.

Free-form prose alone is not eligible for consensus.

## Consequences

### Positive

* Models reduce human review volume without controlling execution.
* Findings can be independently compared.
* Model errors cannot directly authorize a transition.
* Reviewer performance can be measured over time.

### Negative

* Structured-output validation is required.
* Models may produce inconclusive or invalid reports.
* A separate consensus engine is necessary.
* Some high-risk decisions still require human judgment.

## Enforcement

Reviewer model endpoints must not be given execution tools.

Reviewer sessions must use:

* read-only evidence snapshots;
* isolated working directories;
* no governance write credentials;
* no execution-worker credentials;
* no direct consensus-state access.

A reviewer recommendation such as `ACCEPTABLE` must never itself change gate state.
