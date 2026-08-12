# IMPLEMENTATION_ORDER.md

# Hermes Build Order

This document defines the recommended implementation sequence for Hermes. Each phase should be independently testable before progressing.

---

## Phase 0 – Architecture Foundation

Deliverables

- Architecture Handbook
- Architecture Decision Records
- Authority Model
- System Context
- Core schemas

Exit Criteria

- Architecture reviewed
- ADR-0001 through ADR-0004 accepted
- Core terminology frozen

---

## Phase 1 – Hermes Core

Build

- Governance Engine
- State Machine
- Configuration Loader
- Logging
- Error Handling

Exit Criteria

- Valid state transitions only
- Audit logging operational

---

## Phase 2 – Event Bus

Build

- Event schema
- Router
- Correlation IDs
- Idempotency
- Event persistence

Exit Criteria

- Components communicate only through events

---

## Phase 3 – Registry Services

Build

- Agent Registry
- Model Registry
- Policy Registry

Exit Criteria

- All components resolve identities from registries

---

## Phase 4 – Evidence System

Build

- Evidence packages
- Hash generation
- Artifact inventory
- Freeze operation

Exit Criteria

- Immutable evidence packages supported

---

## Phase 5 – Review System

Build

- Reviewer contracts
- Report schema
- Reviewer orchestration
- Validation pipeline

Exit Criteria

- Reviewers cannot execute tools
- Structured reports generated

---

## Phase 6 – Consensus Engine

Build

- Finding normalization
- Agreement evaluation
- Acceptance generation

Exit Criteria

- Deterministic consensus implemented

---

## Phase 7 – Memory Layer

Build

- Obsidian adapter
- Retrieval
- Memory proposals
- Promotion workflow

Exit Criteria

- Canonical memory writes controlled by Hermes

---

## Phase 8 – Operational Projection

Build

- Anytype adapter
- Project dashboards
- Review dashboards

Exit Criteria

- One-way operational projection functional

---

## Phase 9 – Model Runtime

Build

- Ollama adapter
- Model qualification
- Model health monitoring

Exit Criteria

- Registered models callable through Hermes

---

## Phase 10 – User Interface

Build

- LibreChat integration
- Agent selection
- Review presentation
- Status dashboards

Exit Criteria

- Users interact through Hermes APIs

---

## Phase 11 – Restricted Execution

Build

- Open Interpreter adapter
- Execution envelopes
- Path restrictions
- Command restrictions

Exit Criteria

- Authorized execution only

---

## Phase 12 – Multi-Agent Workflows

Build

- Planner
- Researcher
- Reviewer
- Coder
- Verifier
- Publisher

Exit Criteria

- Event-driven workflows with isolated authority

---

## Phase 13 – Hardening

Complete

- Security testing
- Recovery testing
- Performance tuning
- Documentation updates
- Production readiness review

## Guiding Rule

Never implement a later phase by bypassing an earlier architectural control. Governance, evidence, and authority boundaries always precede automation.
