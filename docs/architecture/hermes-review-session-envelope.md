---
title: "Hermes Review Session Envelope"
document_id: "ARCH-HERMES-REVIEW-SESSION-ENVELOPE"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Review Session Envelope

## Purpose

The Hermes review session envelope answers one question:

```text
What exact read-only input package should a future reviewer runner receive?
```

It does not run models, start browser automation, collect reports, perform consensus, authorize execution, or change governance state.

## Implementation

Code:

- `tools/hermes_core/review_session.py`

Tests:

- `tests/hermes_core/test_review_session.py`

## Envelope Contract

The envelope contains:

- review session id
- task id
- evidence package id
- evidence path
- creation timestamp
- read-only flag
- reviewer assignments
- session hash

The session hash covers the full envelope payload except the hash field itself. Any later change to assignments, evidence path, task id, or session metadata invalidates verification.

## Deliberate Limits

The envelope is a frozen input package only. It does not invoke Ollama, GPT, browser automation, ledger writes, Obsidian updates, Anytype updates, or publishing workflows.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 62 tests
OK
```
