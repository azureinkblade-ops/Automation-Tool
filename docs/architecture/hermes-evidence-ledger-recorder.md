---
title: "Hermes Evidence Ledger Recorder"
document_id: "ARCH-HERMES-EVIDENCE-LEDGER-RECORDER"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Evidence Ledger Recorder

## Purpose

The Hermes evidence ledger recorder connects frozen evidence packages to the append-only event ledger.

It records that a specific evidence package is ready for review, without starting a review, executing work, or calling any external system.

## Implementation

Code:

- `tools/hermes_core/evidence_recorder.py`

Tests:

- `tests/hermes_core/test_evidence_recorder.py`

## Recording Rule

The recorder follows one rule:

```text
verify evidence first, write ledger event second
```

If evidence verification fails, the recorder writes no ledger event.

If evidence verification succeeds, the recorder writes exactly one `evidence.frozen` event.

## Ledger Payload

Frozen evidence events include:

- evidence package id
- evidence package SHA-256
- evidence package path
- artifact count
- artifact ids
- actor
- metadata

## Replay

The recorder can replay `evidence.frozen` events and return the latest frozen evidence record by task id.

Replay ignores unrelated ledger events.

## Deliberate Limits

This implementation does not execute work, call external services, invoke reviewers, publish content, call browser automation, write to Anytype, or update Obsidian.

It only records verified evidence package state locally.

## Verification Command

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 30 tests
OK
```

