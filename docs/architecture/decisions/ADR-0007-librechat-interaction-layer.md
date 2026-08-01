# ADR-0007 LibreChat Is the Human-Agent Interaction Layer

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** User interface and agent interaction
* **Related:** ADR-0001

## Context

The system needs a practical interface for:

* selecting agents;
* interacting with local models;
* reviewing outputs;
* attaching evidence;
* accessing tools through controlled interfaces;
* managing conversations;
* presenting review results.

Building a complete custom interface before the governance system is stable would create unnecessary implementation cost.

## Decision

LibreChat will be the primary human-agent interaction layer.

LibreChat may provide:

* conversations;
* agent selection;
* model endpoint selection;
* file attachment;
* temporary conversational context;
* MCP tool presentation;
* review-report presentation;
* user-initiated workflow requests.

LibreChat will not own:

* authoritative governance state;
* consensus;
* execution authorization;
* permanent project truth;
* cryptographic acceptance;
* unrestricted tool access.

LibreChat submits requests to Hermes and displays Hermes results.

## Consequences

### Positive

* A mature user interface is available early.
* Multiple local and remote model endpoints can be presented consistently.
* Agent definitions can be exposed without building a bespoke frontend.
* Hermes can remain UI-independent.

### Negative

* LibreChat configuration becomes an additional managed surface.
* Built-in memory and agent features may overlap with Hermes.
* Care is required to prevent duplicate orchestration.

## Boundary rule

LibreChat is the front door, not the executive authority.

A conversation message cannot itself constitute an accepted authorization unless Hermes validates and records it through the defined governance process.
