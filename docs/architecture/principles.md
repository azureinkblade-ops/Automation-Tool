---
title: "Hermes Architecture Principles"
document_id: "ARCH-PRINCIPLES"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Architecture Principles

## 1. Single governance authority

Hermes is the sole authority for workflow state, gate transitions, acceptance, and authorization validation.

## 2. Evidence before narrative

A claim such as “complete,” “verified,” or “safe” has no governance force unless it is supported by identified evidence.

## 3. Deterministic checks before model judgment

Facts that can be verified mechanically must be verified mechanically before a model reviews meaning or sufficiency.

Examples include:

- hashes;
- schemas;
- file presence;
- package identity;
- authorization expiration;
- Git identity;
- path access;
- command exit status.

## 4. Models review; policy decides

Models may identify findings and recommend dispositions. Models do not issue acceptance, authorization, or human approval.

## 5. Acceptance is not execution

Evidence acceptance and permission to perform a state-changing action are separate transitions and separate artifacts.

## 6. Least authority

Every component receives only the minimum permissions needed for its role.

## 7. Immutable inputs for review

All reviewers must evaluate the same frozen evidence package. A review is invalid if its evidence identity differs.

## 8. Independent review before comparison

Reviewers must not see other reviewers’ conclusions before completing their initial reports.

## 9. Explicit uncertainty

Unknown, unsupported, and ambiguous conditions must be represented explicitly. They must not be silently converted into pass states.

## 10. Fail closed

Missing authorization, invalid evidence, schema errors, path violations, and tool failures block or escalate the workflow.

## 11. Local-first and offline-capable

Core governance, model review, evidence inspection, and knowledge retrieval should function locally whenever practical.

## 12. No hidden authority in editable notes

Markdown notes, chat messages, dashboards, and model prose may inform the system but do not independently authorize state transitions.

## 13. Append-only auditability

Every material state transition must create a durable audit event. Historical state must not be rewritten to make a later result appear inevitable.

## 14. Reproducible identity

Models, environments, dependencies, policies, schemas, and evidence packages must be identified by exact versions or hashes.

## 15. Structured boundaries

Agent-to-agent communication, reviews, authorizations, and execution results must use versioned schemas.

## 16. Human control of high-impact actions

Security policy changes, production activation, irreversible operations, and unresolved high-risk findings require explicit human intervention.

## 17. Canonical knowledge requires promotion

Agent observations do not become durable truth automatically. They enter a proposal, conflict-check, review, and promotion workflow.

## 18. Projection is not authority

Anytype and Obsidian may display state. Only Hermes changes authoritative operational state.

## 19. Replaceable integrations

LibreChat, Ollama, Open Interpreter, Anytype, and Obsidian adapters must be replaceable without redesigning the governance core.

## 20. Test the controls, not merely the happy path

Every authority boundary must have negative tests showing that prohibited actions are rejected.
