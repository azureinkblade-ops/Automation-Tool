---
title: "AUTH-2026-08-01 Hermes Evidence Ledger Recorder"
document_id: "AUTH-2026-08-01-HERMES-EVIDENCE-LEDGER-RECORDER"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Evidence Ledger Recorder

## Authorization Summary

David authorized the next implementation step after completion of the Hermes evidence package builder.

This authorization permits work on the local Hermes evidence ledger recorder only.

## Parent Implementation Basis

Completed implementation:

- Commit `a9bef57`: Add Hermes core validator.
- Commit `df22662`: Add Hermes ledger registry.
- Commit `f96f423`: Add Hermes transition recorder.
- Commit `5f8d890`: Add Hermes evidence package builder.
- `tools/hermes_core/evidence.py`
- `tools/hermes_core/ledger.py`

Verification completed:

- 27 Hermes Core tests pass.
- Evidence packages are frozen and schema-valid.
- Evidence package and artifact mutations are detected.

## Authorized Phase

Phase 2 continuation: evidence package system.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local evidence ledger recorder under `tools/hermes_core/**`.
2. Verify evidence packages before ledger recording.
3. Append exactly one `evidence.frozen` event for verified evidence.
4. Write no ledger event for invalid evidence.
5. Add focused tests for accepted evidence events, invalid evidence rejection, and replay lookup.
6. Document the evidence ledger recorder contract under `docs/architecture/**`.

This approval does not authorize reviewer orchestration, model execution, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for evidence event recording.
- Add documentation updates that explain evidence event behavior.
- Use local-only test fixtures and temporary files under `tests/hermes_core/**`.

## Prohibited Operations

- Do not modify `app.py`.
- Do not publish, schedule, upload, or post social content.
- Do not connect new external services.
- Do not enable autonomous workflows.
- Do not grant model agents execution authority.
- Do not add browser automation.
- Do not write secrets or credentials into repository files.
- Do not delete existing files.

## Permitted Write Paths

- `docs/architecture/**`
- `tools/hermes_core/**`
- `tests/hermes_core/**`

## Network Policy

No network access required.

## Required Exit Criteria

- Verified evidence writes one `evidence.frozen` ledger event.
- Invalid evidence writes no ledger event.
- Replay can find frozen evidence by task id.
- Tests run locally and pass.

