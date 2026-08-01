---
title: "Hermes Memory Model"
document_id: "ARCH-MEMORY"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-07-31"
---

# Hermes Memory Model

## 1. Memory classes

### Conversation memory

Owned by LibreChat.

Contains transient conversational context. It is non-authoritative and may be summarized or discarded.

### Operational memory

Owned by Hermes.

Contains:

- active task state;
- pending reviews;
- current gate;
- authorizations;
- model and agent assignments;
- unresolved findings;
- workflow correlations.

### Durable semantic memory

Owned by canonical Obsidian notes.

Contains:

- architecture;
- rationale;
- runbooks;
- accepted lessons;
- project history;
- fiction canon;
- reusable knowledge.

### Structured projection

Owned by Anytype as a non-authoritative operational view.

## 2. Retrieval policy

Retrieval must be:

- role-scoped;
- project-scoped;
- classification-aware;
- freshness-aware;
- limited by context budget;
- recorded in a retrieval manifest.

## 3. Note classification

Recommended frontmatter:

```yaml
document_status: canonical
authority: approved_reference
project: hermes
sensitivity: internal
reviewed_at: 2026-07-31
source_commit: "<commit>"
```

Draft notes must not be treated as policy.

## 4. Memory proposal schema

```yaml
proposal_id: "mem-uuid"
claim: "..."
project_id: "..."
proposed_destination: "..."
sources:
  - artifact: "..."
    sha256: "..."
confidence: 0.88
conflicts: []
proposed_by: "agent-id"
risk_class: "semantic"
```

## 5. Promotion rules

### Automatic eligibility

Only deterministic, low-risk facts may be auto-promoted if policy allows.

### Review required

Technical conclusions, architectural lessons, and workflow recommendations require review.

### Human required

Security, legal, rights, personal, production, and material canon changes require human confirmation.

## 6. Conflict handling

A conflict does not overwrite existing knowledge. It creates:

- a conflict record;
- source comparison;
- review task;
- resolution decision;
- supersession or amendment link.

## 7. Deduplication

Deduplication must compare:

- semantic similarity;
- exact entities;
- source identity;
- time range;
- existing canonical claims.

## 8. Obsidian write policy

Agents never write directly to canonical folders. Hermes applies accepted memory changes through a controlled adapter.

## 9. Anytype relationship

Anytype receives structured summaries such as:

- proposal status;
- related project;
- destination note;
- reviewer outcome;
- human action required.

## 10. Deletion and retention

Memory deletion must distinguish:

- removal from active retrieval;
- archival;
- correction;
- legal or privacy deletion;
- audit retention.

Audit records should preserve that a change occurred without retaining prohibited content.
