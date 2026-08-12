---
title: "Hermes Evidence Staleness Checker"
document_id: "ARCH-HERMES-EVIDENCE-STALENESS-CHECKER"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Evidence Staleness Checker

## Purpose

The Hermes evidence staleness checker determines whether a frozen evidence package is still eligible for review.

It reports drift without modifying the package, ledger, or source artifacts.

## Implementation

Code:

- `tools/hermes_core/evidence_staleness.py`

Tests:

- `tests/hermes_core/test_evidence_staleness.py`

## Report Rule

The checker follows one rule:

```text
inspect evidence, report drift, do not mutate
```

The report includes:

- evidence package id
- task id
- stale flag
- review eligibility flag
- package hash mismatch flag
- schema-valid flag
- artifact status rows
- issue messages

## Artifact Statuses

Artifact rows may be:

- `ok`
- `missing`
- `changed`

Any `missing` or `changed` artifact makes the package stale and not review eligible.

Any package hash mismatch or schema invalidity also makes the package stale and not review eligible.

## Deliberate Limits

This implementation does not execute work, call external services, invoke reviewers, publish content, call browser automation, write to Anytype, update Obsidian, or append ledger events.

It only reports whether a local evidence package is still trustworthy.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 34 tests
OK
```

