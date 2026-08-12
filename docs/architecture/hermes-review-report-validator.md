---
title: "Hermes Review Report Validator"
document_id: "ARCH-HERMES-REVIEW-REPORT-VALIDATOR"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Review Report Validator

## Purpose

The Hermes review report validator answers one question:

```text
Is this review report safe to accept as reviewer evidence?
```

It does not accept work, authorize execution, change task state, call models, or start browser automation.

## Implementation

Code:

- `tools/hermes_core/review_report.py`

Tests:

- `tests/hermes_core/test_review_report.py`

## Validation Contract

The validator checks:

- the report satisfies the `hermes.review` schema
- the report binds to the same task id as the frozen evidence package
- the report binds to the same evidence package id
- every finding reference points to an artifact in the frozen evidence package
- finding ids are unique inside the report
- `completed_at` is not earlier than `started_at`
- a recommendation is present for downstream review decisions
- reviewer authority flags remain false

## Decision Shape

The validator returns a local result object with:

- valid flag
- review id
- task id
- evidence package id
- reviewer agent id
- recommendation
- finding count
- issue list

## Deliberate Limits

This implementation validates reviewer output only. It does not run reviewers, combine reports, perform consensus, authorize execution, update external systems, or write to the Hermes ledger.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 45 tests
OK
```
