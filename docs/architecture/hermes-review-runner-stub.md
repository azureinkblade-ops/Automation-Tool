---
title: "Hermes Review Runner Stub"
document_id: "ARCH-HERMES-REVIEW-RUNNER-STUB"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Review Runner Stub

## Purpose

The Hermes review runner stub answers one question:

```text
Can a review session envelope be accepted by the future runner boundary?
```

It verifies the envelope and returns a pending result. It does not invoke any model.

## Implementation

Code:

- `tools/hermes_core/review_runner.py`

Tests:

- `tests/hermes_core/test_review_runner.py`

## Runner Boundary

The stub accepts:

- a frozen review session envelope object
- a path to a frozen review session envelope

It verifies the session hash and read-only contract, then returns:

- pending status
- review session id
- task id
- evidence package id
- assignment count
- reason that model execution is not authorized

## Deliberate Limits

This is not reviewer orchestration. It does not call Ollama, GPT, browser automation, external APIs, execution workers, ledger writes, Obsidian updates, or publishing workflows.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 65 tests
OK
```
