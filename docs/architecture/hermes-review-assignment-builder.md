---
title: "Hermes Review Assignment Builder"
document_id: "ARCH-HERMES-REVIEW-ASSIGNMENT-BUILDER"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Review Assignment Builder

## Purpose

The Hermes review assignment builder answers one question:

```text
Which active reviewers should review this frozen evidence package?
```

It does not run models, start reviewer sessions, collect reports, perform consensus, authorize execution, or change governance state.

## Implementation

Code:

- `tools/hermes_core/review_assignment.py`

Tests:

- `tests/hermes_core/test_review_assignment.py`

## Assignment Contract

The builder checks:

- evidence is eligible for review through `ReviewEligibilityGate`
- active reviewers are available through `ReviewerRegistry`
- minimum active reviewer count is satisfied
- requested review roles are known

If the plan is ready, it returns deterministic reviewer assignments with:

- reviewer agent id
- model id
- review role
- evidence package id

## Deliberate Limits

The builder creates a local plan only. It does not call Ollama, invoke GPT, launch browser automation, write the ledger, update Obsidian, start review tasks, or publish content.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 57 tests
OK
```
