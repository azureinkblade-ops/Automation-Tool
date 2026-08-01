---
title: "Hermes Transition Recorder"
document_id: "ARCH-HERMES-TRANSITION-RECORDER"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Transition Recorder

## Purpose

The Hermes transition recorder is the first local workflow that connects schema validation, state-machine validation, and ledger persistence.

It turns a proposed state change into an auditable governance event only after the transition passes deterministic validation.

## Implementation

Code:

- `tools/hermes_core/transition_recorder.py`

Tests:

- `tests/hermes_core/test_transition_recorder.py`

## Recording rule

The recorder follows one rule:

```text
validate transition first, write ledger event second
```

If validation fails, the recorder writes no ledger entry.

If validation succeeds, the recorder writes exactly one `governance.transition.accepted` event.

## Ledger payload

Accepted transition events include:

- from state
- to state
- task id
- actor
- artifact references
- metadata
- transition SHA-256

Artifact references may include:

- parent event or artifact reference
- task id
- evidence package id and hash
- review ids
- consensus id and result
- acceptance id and hash
- authorization id and hash
- parent acceptance hash
- execution id

## Replay

The recorder can replay transition events and reconstruct the latest known task state by applying accepted transition events in ledger order.

Replay ignores unrelated ledger events.

## Deliberate limits

This implementation does not execute work, call external services, publish content, call browser automation, write to Anytype, or update Obsidian.

It only records validated governance state transitions locally.

## Verification

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 21 tests
OK
```
