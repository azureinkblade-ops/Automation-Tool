---
title: "Hermes Core Validator"
document_id: "ARCH-HERMES-CORE-VALIDATOR"
version: "0.1.0"
status: "implemented"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-01"
---

# Hermes Core Validator

## Purpose

The Hermes Core validator is the first executable guard for the agent-to-agent governance pipeline.

It validates lightweight YAML governance contracts and enforces the state-machine boundary created by ADR-0001 through ADR-0004:

- Hermes owns governance state.
- Reviewer models remain review-only.
- Consensus can create acceptance results but cannot authorize execution.
- Acceptance and execution authorization are separate.

## Implementation

Code:

- `tools/hermes_core/schemas.py`
- `tools/hermes_core/state_machine.py`

Tests:

- `tests/hermes_core/test_state_machine.py`

## Validator responsibilities

The validator:

1. Loads schema contracts from `docs/architecture/schemas/*.schema.yaml`.
2. Validates required fields, enums, const values, nested objects, arrays, and date-time strings.
3. Allows only documented transitions from `docs/architecture/state-machine.md`.
4. Rejects prohibited shortcuts such as `ACCEPTED -> AUTHORIZED` and `ACCEPTED -> EXECUTING`.
5. Requires acceptance artifacts before `AWAITING_EXECUTION_AUTHORIZATION`.
6. Requires authorization artifacts before `AUTHORIZED` or `EXECUTING`.
7. Requires `authorization.parent_acceptance_sha256` to match the referenced acceptance artifact.
8. Rejects expired authorization artifacts.
9. Rejects reviewer records that claim authority to modify governance state or authorize execution.

## Deliberate limits

This implementation does not execute work, call external services, publish content, update `app.py`, or connect to Anytype or Obsidian adapters.

It is a local-only governance guard that future pipeline pieces must pass before any worker can be invoked.

## Verification

Run:

```powershell
python -m unittest discover -s tests\hermes_core -v
```

Expected result:

```text
Ran 9 tests
OK
```
