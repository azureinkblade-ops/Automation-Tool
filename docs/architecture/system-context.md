---
title: "Hermes System Context"
document_id: "ARCH-CONTEXT"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes System Context

## 1. System mission

Hermes coordinates local and optionally remote AI agents while preserving explicit authority boundaries, evidence integrity, reproducibility, and human control.

The system is not merely a chatbot. It is an executive control and governance layer that manages:

- agent identity and authority;
- model identity and qualification;
- task and gate state;
- evidence packages;
- independent model reviews;
- deterministic consensus;
- execution authorization;
- restricted local execution;
- operational and durable memory;
- audit history.

## 2. System boundary

Hermes includes the following logical capabilities:

- Governance Engine
- State Machine
- Authorization Engine
- Consensus Engine
- Event Router
- Evidence Registry
- Agent Registry
- Model Registry
- Memory Gateway
- Integration Adapters
- Audit Ledger
- API

Hermes does not include the internal implementation of LibreChat, Ollama, Obsidian, Anytype, or Open Interpreter. Those systems are external integrations.

## 3. Actors

### Human operator

The human operator may:

- create or amend governance policy;
- issue explicit execution authorization;
- resolve escalated findings;
- accept architectural decisions;
- revoke permissions;
- inspect and correct system state through governed procedures.

### Reviewer models

Reviewer models receive immutable evidence snapshots and return structured reports. They have no execution or approval authority.

### Execution models

Execution-capable models may plan or interpret an authorized task, but their actions are constrained by a machine-enforced execution envelope.

### External tools

External tools provide user interfaces, model serving, knowledge storage, projections, or local command execution.

## 4. External systems

### LibreChat

Primary human-agent interaction surface. It may present agents, conversations, reports, and tool requests. It does not own governance state.

### Ollama

Initial local model-serving runtime. It serves registered, qualified model identities.

### Obsidian

Canonical long-term semantic knowledge system for architecture, rationale, runbooks, project history, and domain knowledge.

### Anytype

Structured operational projection for dashboards, objects, relationships, and human work queues.

### Open Interpreter

Restricted execution worker used only with a validated execution envelope.

### OpenJarvis

Deferred optional orchestration framework. It may be evaluated later after Hermes event and authority contracts are stable.

## 5. Context diagram

```text
+------------------+
|  Human Operator  |
+---------+--------+
          |
          v
+------------------+        +------------------+
|    LibreChat     |------->|    Hermes API    |
+------------------+        +---------+--------+
                                      |
                    +-----------------+------------------+
                    |                 |                  |
                    v                 v                  v
             +-------------+   +-------------+   +-------------+
             |   Ollama    |   |  Obsidian   |   |   Anytype   |
             | model serve |   | knowledge   |   | projection  |
             +-------------+   +-------------+   +-------------+
                    |
                    v
             +------------------+
             | Open Interpreter |
             | restricted work  |
             +------------------+
```

## 6. Trust boundaries

### Boundary A: Human interaction to governance

LibreChat messages are untrusted requests until Hermes validates identity, scope, and required confirmation.

### Boundary B: Model output to authoritative state

All model output is untrusted until schema validation, evidence binding, and policy evaluation complete.

### Boundary C: Governance to execution

Execution requires a separately validated authorization envelope. Acceptance alone cannot cross this boundary.

### Boundary D: Knowledge retrieval

Obsidian and Anytype content must be scoped, classified, and snapshotted before entering a reviewer context.

### Boundary E: Local machine access

Open Interpreter and other workers must operate within path, command, network, environment, and timeout restrictions.

## 7. Source-of-truth hierarchy

| Information | Authoritative source |
|---|---|
| Current workflow state | Hermes state store |
| Gate acceptance | Hermes acceptance artifact |
| Execution authorization | Hermes authorization artifact |
| Audit history | Append-only Hermes event ledger |
| Evidence identity | Evidence manifest and root hash |
| Architecture intent | Repository handbook and accepted ADRs |
| Long-term human-readable knowledge | Canonical Obsidian notes |
| Operational dashboards | Anytype projection |
| Conversation history | LibreChat, non-authoritative |
| Installed model runtime | Ollama, qualified through Hermes registry |

## 8. Deployment assumptions

Initial deployment is a single Windows workstation with:

- local repositories;
- local Ollama service;
- local Hermes service;
- local Obsidian vault;
- local Anytype desktop/API;
- LibreChat deployed locally;
- Open Interpreter isolated as a worker process.

The design must not assume permanent network availability.

## 9. Primary system flows

1. User submits a request through LibreChat.
2. Hermes resolves task identity and authority.
3. Deterministic validators inspect artifacts.
4. Evidence is frozen and hash-bound.
5. Independent reviewer models produce reports.
6. Hermes validates and normalizes reports.
7. Deterministic consensus produces a disposition.
8. If accepted, the system waits for separate execution authorization.
9. A restricted worker executes only the authorized scope.
10. Results are frozen, reviewed, and projected into Obsidian or Anytype as appropriate.

## 10. Out-of-scope for the initial implementation

- autonomous production deployment;
- unrestricted web or filesystem access;
- model-generated human signatures;
- self-modifying governance;
- automatic promotion of semantic model conclusions into canonical memory;
- distributed multi-host execution;
- majority-vote acceptance without measured reviewer calibration.
