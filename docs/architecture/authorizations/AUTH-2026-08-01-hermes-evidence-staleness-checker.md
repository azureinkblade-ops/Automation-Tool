---
title: "AUTH-2026-08-01 Hermes Evidence Staleness Checker"
document_id: "AUTH-2026-08-01-HERMES-EVIDENCE-STALENESS-CHECKER"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Evidence Staleness Checker

## Authorization Summary

David authorized the next implementation step after completion of the Hermes evidence ledger recorder.

This authorization permits work on local evidence staleness detection only.

## Parent Implementation Basis

Completed implementation:

- Commit `a9bef57`: Add Hermes core validator.
- Commit `df22662`: Add Hermes ledger registry.
- Commit `f96f423`: Add Hermes transition recorder.
- Commit `5f8d890`: Add Hermes evidence package builder.
- Commit `926daff`: Add Hermes evidence ledger recorder.
- `tools/hermes_core/evidence.py`
- `tools/hermes_core/evidence_recorder.py`

Verification completed:

- 30 Hermes Core tests pass.
- Valid evidence packages can be recorded as `evidence.frozen` events.
- Invalid evidence writes no ledger event.

## Authorized Phase

Phase 2 continuation: stale-dependency detection.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local evidence staleness checker under `tools/hermes_core/**`.
2. Report package hash mismatch without mutating the package.
3. Report missing artifacts.
4. Report changed artifact hashes.
5. Report whether review remains eligible.
6. Add focused tests for clean evidence, changed evidence, missing evidence, and tampered package content.
7. Document the staleness checker contract under `docs/architecture/**`.

This approval does not authorize reviewer orchestration, model execution, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for stale evidence reporting.
- Add documentation updates that explain stale evidence behavior.
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

- Clean evidence reports as not stale and review eligible.
- Changed artifact reports as stale and not review eligible.
- Missing artifact reports as stale and not review eligible.
- Package hash mismatch reports as stale and not review eligible.
- Tests run locally and pass.

