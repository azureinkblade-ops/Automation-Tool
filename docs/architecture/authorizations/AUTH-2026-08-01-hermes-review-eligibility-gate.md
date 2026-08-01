---
title: "AUTH-2026-08-01 Hermes Review Eligibility Gate"
document_id: "AUTH-2026-08-01-HERMES-REVIEW-ELIGIBILITY-GATE"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Review Eligibility Gate

## Authorization Summary

David authorized the next implementation step after completion of the Hermes evidence staleness checker.

This authorization permits work on a local review eligibility gate only.

## Parent Implementation Basis

Completed implementation:

- Commit `a9bef57`: Add Hermes core validator.
- Commit `df22662`: Add Hermes ledger registry.
- Commit `f96f423`: Add Hermes transition recorder.
- Commit `5f8d890`: Add Hermes evidence package builder.
- Commit `926daff`: Add Hermes evidence ledger recorder.
- Commit `37a6acb`: Add Hermes evidence staleness checker.
- `tools/hermes_core/state_machine.py`
- `tools/hermes_core/evidence_staleness.py`

Verification completed:

- 34 Hermes Core tests pass.
- Clean frozen evidence reports as review eligible.
- Stale evidence reports as not review eligible.

## Authorized Phase

Phase 2 completion support: review eligibility gating.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local review eligibility gate under `tools/hermes_core/**`.
2. Use the staleness checker to block stale evidence.
3. Use the deterministic transition validator to confirm `READY_FOR_REVIEW -> UNDER_REVIEW`.
4. Return structured gate decisions with reasons.
5. Add focused tests for eligible review, stale evidence, wrong state, and missing parent reference.
6. Document the review eligibility gate contract under `docs/architecture/**`.

This approval does not authorize reviewer orchestration, model execution, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for review eligibility decisions.
- Add documentation updates that explain gate behavior.
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

- Clean evidence in `READY_FOR_REVIEW` reports eligible.
- Stale evidence reports blocked.
- Wrong source state reports blocked.
- Missing parent reference reports blocked.
- Tests run locally and pass.

