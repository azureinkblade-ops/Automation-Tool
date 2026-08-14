---
title: "Hermes Architecture Handbook"
document_id: "ARCH-README"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Architecture Handbook

## Purpose

This handbook defines the architecture, authority boundaries, operating principles, information flows, and implementation direction for the Hermes agent platform.

Hermes is designed as a local-first, evidence-bound orchestration and governance system for multiple models, tools, knowledge systems, and execution workers. The architecture separates reasoning, review, acceptance, authorization, execution, memory, and user interaction so that no probabilistic model can silently become an execution or governance authority.

## Intended audience

This handbook is intended for:

- the system owner;
- implementation agents;
- reviewer models;
- security reviewers;
- maintainers;
- future contributors;
- operators investigating incidents or disputed state transitions.

## Documentation map

| Document | Purpose |
|---|---|
| [system-context.md](system-context.md) | System boundary, actors, external systems, trust boundaries, and source-of-truth hierarchy |
| [principles.md](principles.md) | Architectural principles that constrain design and implementation |
| [authority-model.md](authority-model.md) | Who may decide, review, authorize, execute, or write |
| [state-machine.md](state-machine.md) | Deterministic governance states, allowed transitions, and prohibited shortcuts |
| [hermes-core-validator.md](hermes-core-validator.md) | Executable schema and state-transition guard for the first governance core |
| [hermes-ledger-registry.md](hermes-ledger-registry.md) | Local append-only ledger and artifact registry for auditable governance state |
| [hermes-transition-recorder.md](hermes-transition-recorder.md) | Validated transition recording and latest-state replay |
| [hermes-evidence-package-builder.md](hermes-evidence-package-builder.md) | Frozen evidence package creation and verification |
| [hermes-evidence-ledger-recorder.md](hermes-evidence-ledger-recorder.md) | Verified evidence package ledger recording |
| [hermes-evidence-staleness-checker.md](hermes-evidence-staleness-checker.md) | Stale evidence and review eligibility reporting |
| [hermes-review-eligibility-gate.md](hermes-review-eligibility-gate.md) | Local gate for deciding whether review may begin |
| [hermes-review-report-validator.md](hermes-review-report-validator.md) | Local validation for reviewer reports bound to frozen evidence |
| [hermes-reviewer-registry.md](hermes-reviewer-registry.md) | Local reviewer identity and authority registry |
| [hermes-review-assignment-builder.md](hermes-review-assignment-builder.md) | Local assignment planning for eligible evidence and active reviewers |
| [hermes-review-session-envelope.md](hermes-review-session-envelope.md) | Frozen read-only input package for future reviewer runners |
| [hermes-review-runner-stub.md](hermes-review-runner-stub.md) | Non-executing boundary for future reviewer model runners |
| [hermes-review-outcome-record.md](hermes-review-outcome-record.md) | Local review outcome record bound to frozen evidence and validated review reports |
| [hermes-finding-normalizer.md](hermes-finding-normalizer.md) | Deterministic normalized finding set built from validated review reports |
| [hermes-consensus-evaluator.md](hermes-consensus-evaluator.md) | Deterministic agreement/disagreement classification over a normalized finding set |
| [hermes-consensus-disposition.md](hermes-consensus-disposition.md) | Deterministic terminal consensus disposition mapping under frozen ADR-0003 policy |
| [hermes-acceptance-artifact.md](hermes-acceptance-artifact.md) | Immutable acceptance artifact binding the full evidence chain from a verified 6C ACCEPTED disposition |
| [hermes-governance-store.md](hermes-governance-store.md) | SQLite authoritative governance store, hash-linked ledger, and governed state integration (Phase 6E) |
| [hermes-governance-runtime.md](hermes-governance-runtime.md) | Runtime store wiring seam + first real governance consumer: `get_governance_store()`, `get_task_governance_status()`, DB path resolution, runtime integration + consumer integration proof |
| [hermes-execution-authorization-handoff.md](hermes-execution-authorization-handoff.md) | Execution Authorization Handoff design + EA-1/EA-2 implementation status: separate authority domain from governance acceptance; ExecutionAuthorization artifact binds to AcceptanceArtifact; EA-1 (domain model + schemas) COMPLETE; EA-2 (separate execution_authority.db persistence + hash-linked integrity ledger) COMPLETE; EA-3..EA-7 future. EA-4B claim consumption + execution attempt COMPLETE (atomic Claim -> ExecutionAttempt consumption; durable ExecutionAttempt; schema v5; concurrency proof 500 trials; 6 mutation teeth; no WorkerRouter/execution). |
| [hermes-execution-authorization-issuance.md](hermes-execution-authorization-issuance.md) | EA-3D issuance design (DESIGN ONLY, no implementation): trust boundary, authority principal matrix, request/decision/atomic-grant prerequisites, domain + store amendment assessment, threat model, security invariants, EA-3I phase slices. EA-3A domain binding amendment COMPLETE + persistence-integrity corrected (Authorization/Decision now cryptographically bind to Request via request_id/request_hash/decision_id/decision_hash; artifact_version 2; authority DB schema v2, v1 fails closed; authorization_id tamper-evident via decision_linkage_sha256 envelope). EA-3B atomic store amendment COMPLETE (storage-only: record_granted_decision_and_authorization one-transaction atomic grant, request-keyed reads, UNIQUE(request_id) per request for decision + authorization, request_linkage_sha256 tamper envelope, replay conflict/idempotency, rollback zero-residue, orphan detection; authority DB schema v3, v1/v2 fail closed; NO issuance service, no claim, no worker, no execution transition). EA-3I.1 policy + authority evaluation contracts COMPLETE (pre-capability: deterministic versioned ExecutionAuthorizationPolicy registry from policies/*.yaml; pure/read-only evaluate_execution_authorization_policy with ALLOW/DENY/REQUIRES_HUMAN; HUMAN eligible only when authenticated + recognized role, POLICY_SERVICE requires human unless enumerated auto-scope, SYSTEM never grants; fail-closed unknown op/worker; scope never widened; read-only acceptance prerequisite; no ExecutionAuthorization persisted). EA-3I.2 capability-bearing issuance COMPLETE (first slice permitted to create real execution authority: issue_execution_authorization(...) reads persisted Request, verifies hash + exact AcceptanceArtifact binding, authenticates/validates deciding actor, resolves frozen policy, reuses EA-3I.1 evaluator, persists DENIED Decision via record_decision or matched GRANTED Decision + ExecutionAuthorization via EA-3B record_granted_decision_and_authorization; injected UTC clock, non-null expires_at, secrets.token_hex nonce, replay idempotency; no ExecutionClaim, no ExecutionAttempt, no worker, no execution transition, no app.py integration). EA-4A claim domain + atomic claim persistence COMPLETE (first slice permitted to create a durable ExecutionClaim: ExecutionClaim immutably binds authorization_id/authorization_hash/request_id/request_hash/decision_id/decision_hash/task_id; structured Claimant; claimed_at + claim_expires_at absolute UTC Z, claim_expires_at > claimed_at non-null bounded <= 300s; claim-time Authorization existence/integrity/expiry prerequisites (claimed_at < authorization.expires_at, equal/later BLOCKED); one Claim per Authorization via UNIQUE(authorization_id) + service replay/conflict (exact replay returns existing, different claimant CONFLICT, no transfer); claim_authorization_atomically(...) one transaction with CLAIM_RECORDED ledger event, injected post-row failure leaves zero residue; claim reads fail closed on claim_linkage_sha256 tamper; authority DB schema v4 (v3/v2/v1/unsupported fail closed, no silent migration); no ExecutionAttempt, no WorkerRouter, no worker launch/enqueue/dispatch, no subprocess, no EXECUTING, no app.py integration, no automatic claim after issuance). | EA-4B claim consumption + execution attempt COMPLETE (atomic Claim -> ExecutionAttempt consumption; durable ExecutionAttempt; schema v5; concurrency proof 500 trials; 6 mutation teeth; no WorkerRouter/execution). |

| [decisions/ADR-0013-execution-authority-separate-from-governance.md](decisions/ADR-0013-execution-authority-separate-from-governance.md) | ADR-0013: execution authority is a separate domain/persistence (Option B) bound by hash to AcceptanceArtifact; fail-closed integrity |
| [glossary.md](glossary.md) | Canonical terminology |
| [architecture-roadmap.md](architecture-roadmap.md) | Phased implementation sequence and exit criteria |
| [component-model.md](component-model.md) | Component responsibilities and interfaces |
| [data-flow.md](data-flow.md) | Request, evidence, review, memory, and execution flows |
| [event-model.md](event-model.md) | Versioned messages, routing, idempotency, and event handling |
| [security-model.md](security-model.md) | Trust zones, permissions, secrets, isolation, and audit controls |
| [memory-model.md](memory-model.md) | Conversation, operational, and durable knowledge memory |
| [review-model.md](review-model.md) | Deterministic validation, reviewer reports, and consensus |
| [execution-model.md](execution-model.md) | Execution envelopes and restricted workers |
| [integration-model.md](integration-model.md) | LibreChat, Ollama, Obsidian, Anytype, and Open Interpreter |
| [repository-layout.md](repository-layout.md) | Recommended source, schema, evidence, and documentation layout |
| [schemas/README.md](schemas/README.md) | Core governance object contracts for the agent-to-agent pipeline |
| [technology-stack.md](technology-stack.md) | Initial technology choices and replacement boundaries |
| [quality-attributes.md](quality-attributes.md) | Reliability, auditability, security, portability, and performance |
| [threat-model.md](threat-model.md) | Assets, threats, mitigations, and residual risks |
| [decisions/README.md](decisions/README.md) | ADR index and lifecycle rules |

## Document authority

The repository-tracked handbook is authoritative for architecture intent. It is not itself an execution authorization.

The authority hierarchy is:

1. active runtime governance and authorization artifacts;
2. Hermes operational state and append-only audit history;
3. repository-tracked policies, schemas, ADRs, and this handbook;
4. canonical Obsidian knowledge;
5. Anytype operational projections;
6. LibreChat conversations and transient agent context.

A lower layer may summarize a higher layer but may not override it.

## Document lifecycle

Documents begin as `proposed`. They become `accepted` only after review. Material changes to accepted architecture should be recorded through an ADR or an explicitly versioned amendment.

Permitted lifecycle values:

- `draft`
- `proposed`
- `accepted`
- `deprecated`
- `superseded`
- `rejected`
- `archived`

## Writing conventions

Normative terms have the following meaning:

- **MUST**: mandatory for conformance.
- **MUST NOT**: prohibited.
- **SHOULD**: recommended unless a documented exception exists.
- **MAY**: optional.
- **AUTHORITATIVE**: the controlling source for a decision or state.
- **PROJECTION**: a readable or visual representation that cannot independently change authoritative state.

## Architecture summary

```text
User
  |
  v
LibreChat
  |
  v
Hermes Governance Core
  |-- State and authorization
  |-- Event routing
  |-- Evidence registry
  |-- Reviewer orchestration
  |-- Deterministic consensus
  |-- Memory gateway
  |
  +--> Ollama reviewer and worker models
  +--> Obsidian durable knowledge
  +--> Anytype operational projection
  +--> Open Interpreter restricted execution worker
```

## Initial implementation constraint

Implementation begins with deterministic contracts and state handling. Model orchestration, user interfaces, and execution workers are integrated only after authority, evidence, and transition rules have executable tests.
