---
title: "Hermes Review Eligibility Gate"
document_id: "ARCH-HERMES-REVIEW-ELIGIBILITY-GATE"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Review Eligibility Gate

## Purpose

The Hermes review eligibility gate answers one question:

```text
Can this task enter review now?
```

It combines evidence freshness with the deterministic state-machine transition rule.

## Implementation

Code:

- `tools/hermes_core/review_gate.py`

Tests:

- `tests/hermes_core/test_review_gate.py`

## Gate Rule

The gate follows one rule:

```text
fresh evidence plus valid transition allows review
```

The gate checks:

- current state is allowed to transition to `UNDER_REVIEW`
- parent event or artifact reference exists
- evidence package can be loaded
- evidence package is not stale
- evidence package validates against `hermes.evidence`

## Decision Shape

The gate returns a local decision object with:

- eligible flag
- from state
- target state
- task id
- evidence package id
- reasons
- staleness report

## Deliberate Limits

This implementation does not start reviewers, call models, execute work, call external services, publish content, call browser automation, write to Anytype, update Obsidian, or append ledger events.

It only decides whether review may begin.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 38 tests
OK
```

