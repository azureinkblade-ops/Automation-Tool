---
title: "Hermes Architecture Glossary"
document_id: "ARCH-GLOSSARY"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Architecture Glossary

## Acceptance

A deterministic governance result stating that a specific evidence package satisfies a specific review policy. Acceptance does not authorize execution.

## Agent

A registered reasoning role with a model, authority class, context scope, tool scope, and output contract.

## Anytype projection

A structured operational representation of Hermes data used for dashboards and relationships. It is non-authoritative.

## Artifact

A file, record, report, model package, manifest, or other identified output used by the workflow.

## Authorization

A bounded permission to perform specified operations under specified constraints.

## Canonical knowledge

Reviewed, durable, human-readable knowledge that the system may rely on for context. Canonical knowledge is not necessarily runtime authority.

## Consensus

A deterministic comparison of validated independent reviewer reports against a frozen policy.

## Deterministic validator

Code that checks mechanically verifiable conditions without model judgment.

## Evidence package

A frozen set of artifacts with an inventory and root identity used as the input to review.

## Evidence root

The cryptographic identity representing the exact contents and ordering of an evidence package.

## Execution envelope

A machine-readable authorization describing permitted operations, paths, tools, network behavior, timeouts, and expected outputs.

## Finding

A reviewer or validator observation linked to a rule, subject, severity, evidence, and disposition.

## Frozen fixture

A test input whose identity is fixed and whose use is restricted by a gate or authorization policy.

## Gate

A governed transition boundary that requires specified evidence and policy conditions.

## Governance

Rules and mechanisms that determine valid state transitions, authority, and execution scope.

## Hermes

The authoritative governance and orchestration core.

## Human confirmation

An explicit human decision recorded with scope and evidence identity.

## Inconclusive

A terminal review outcome indicating that sufficient valid review information was not produced.

## Manifest

A structured inventory of artifacts, identities, versions, and hashes.

## Memory proposal

A candidate durable knowledge entry that has not yet been promoted to canonical memory.

## Model registry

The authoritative catalog of model identities, revisions, roles, qualifications, and status.

## Operational memory

Hermes-owned state needed to continue active workflows.

## Projection

A non-authoritative copy or view derived from authoritative data.

## Promotion

The controlled transition of a memory proposal into canonical durable knowledge.

## Reviewer model

A model with read-only authority that produces an evidence-bound review report.

## Review contract

The schema, rules, scope, and expectations supplied to an independent reviewer.

## Scope violation

An attempted action outside the paths, commands, tools, data, or operations authorized for a task.

## Source of truth

The controlling system or artifact for a category of information.

## State transition

A validated movement from one workflow state to another.

## Terminal state

A workflow result that stops the current transition chain, such as `ACCEPTED`, `ESCALATED`, `BLOCKED`, or `INCONCLUSIVE`.

## Trust boundary

A boundary across which inputs must be treated as untrusted until validated.

## Worker

A component that performs authorized operations and returns evidence, without approval authority.
