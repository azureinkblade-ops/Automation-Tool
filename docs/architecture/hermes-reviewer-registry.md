---
title: "Hermes Reviewer Registry"
document_id: "ARCH-HERMES-REVIEWER-REGISTRY"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Reviewer Registry

## Purpose

The Hermes reviewer registry answers one question:

```text
Which local reviewer identities are allowed to submit review reports?
```

It does not run models, start reviews, perform consensus, authorize execution, or change governance state.

## Implementation

Code:

- `tools/hermes_core/reviewer_registry.py`

Tests:

- `tests/hermes_core/test_reviewer_registry.py`

## Registry Contract

Reviewer records must satisfy the existing `hermes.agent` schema and the stricter reviewer-only constraints:

- `role` must be `reviewer`
- `authority.can_review` must be `true`
- `authority.can_modify_governance_state` must be `false`
- `authority.can_authorize_execution` must be `false`
- `authority.can_execute` must be `false`
- `agent_id` values must be unique

The registry may be loaded from either:

- a JSON array of reviewer records
- a JSON object with a `reviewers` array

## Query Shape

The registry supports:

- lookup by reviewer agent id
- active reviewer listing
- minimum active reviewer count checks

## Deliberate Limits

The registry is identity and authority metadata only. It does not call Ollama, invoke GPT, call browser automation, write the ledger, update Obsidian, or publish content.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 52 tests
OK
```
