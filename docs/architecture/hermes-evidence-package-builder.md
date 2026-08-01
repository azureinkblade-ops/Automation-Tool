---
title: "Hermes Evidence Package Builder"
document_id: "ARCH-HERMES-EVIDENCE-PACKAGE-BUILDER"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Evidence Package Builder

## Purpose

The Hermes evidence package builder creates frozen, hash-bound material for later review.

It gives reviewers and validators one immutable evidence identity instead of a loose set of files.

## Implementation

Code:

- `tools/hermes_core/evidence.py`

Tests:

- `tests/hermes_core/test_evidence_package.py`

## Package Rule

The builder follows one rule:

```text
inventory files first, freeze package second
```

Each evidence package contains:

- evidence package id
- task id
- created timestamp
- inventory of artifacts
- SHA-256 for every artifact
- package SHA-256
- frozen flag

The package SHA-256 is calculated from the canonical package content before the hash field is inserted.

## Verification

Verification checks:

- package schema validity
- package SHA-256
- frozen flag
- every inventoried artifact still exists
- every inventoried artifact still matches its recorded SHA-256

If a package file or inventoried artifact changes, verification fails.

## Deliberate Limits

This implementation does not execute work, call external services, invoke reviewers, publish content, call browser automation, write to Anytype, or update Obsidian.

It only creates and verifies local evidence packages.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 27 tests
OK
```
