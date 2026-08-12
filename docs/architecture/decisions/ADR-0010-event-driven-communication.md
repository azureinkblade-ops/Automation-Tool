# ADR-0010 Agent Communication Uses Versioned Events and Messages

* **Status:** Proposed
* **Date:** 2026-07-31
* **Decision owners:** David Powell
* **Scope:** Agent-to-agent communication
* **Related:** ADR-0001

## Context

Direct agent-to-agent calls create hidden coupling, recursive loops, untracked context transfer, and unclear authority.

The architecture includes planners, reviewers, researchers, coders, execution workers, memory services, and external interfaces.

## Decision

Inter-component and agent-to-agent communication will use versioned, structured events or message envelopes.

An agent must not directly invoke another agent without producing a Hermes-routed message.

Each message must contain:

* schema version;
* message ID;
* workflow ID;
* sender;
* recipient or routing class;
* message type;
* task scope;
* input artifact identities;
* authorization identity where applicable;
* expected response schema;
* hop count;
* visited components;
* timestamp.

## Loop prevention

Hermes must enforce:

* maximum hop count;
* visited-agent tracking;
* duplicate message detection;
* idempotency keys;
* recursion limits;
* terminal state checks.

## Consequences

### Positive

* Workflows are traceable.
* Components can be replaced independently.
* Recursive calls can be detected.
* Events can drive Anytype projections and Obsidian summaries.

### Negative

* More schema design is required.
* Debugging shifts from call stacks to event traces.
* Schema migration must be managed.

## OpenJarvis position

OpenJarvis is deferred as an optional orchestration component.

It may later consume and produce Hermes-compatible messages, but it will not be introduced until the Hermes event contract and single-worker flow are stable.
