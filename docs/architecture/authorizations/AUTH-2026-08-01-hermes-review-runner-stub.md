---
title: "AUTH-2026-08-01 Hermes Review Runner Stub"
document_id: "AUTH-2026-08-01-HERMES-REVIEW-RUNNER-STUB"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Review Runner Stub

## Authorization Summary

David authorized continuing the Hermes agent-to-agent governance rebuild after the review session envelope builder.

This authorization permits a local non-executing review runner interface stub only.

## Parent Implementation Basis

Completed implementation:

- Commit `a9bef57`: Add Hermes core validator.
- Commit `df22662`: Add Hermes ledger registry.
- Commit `f96f423`: Add Hermes transition recorder.
- Commit `5f8d890`: Add Hermes evidence package builder.
- Commit `926daff`: Add Hermes evidence ledger recorder.
- Commit `37a6acb`: Add Hermes evidence staleness checker.
- Commit `8fb4c7b`: Add Hermes review eligibility gate.
- Commit `6a94c77`: Add Hermes review report validator.
- Commit `10ae515`: Add Hermes reviewer registry.
- Commit `964ab14`: Add Hermes review assignment builder.
- Commit `a7cfc0b`: Add Hermes review session envelope.
- `tools/hermes_core/review_session.py`

Verification completed:

- 62 Hermes Core tests pass.
- Review session envelopes can be frozen and verified.

## Authorized Phase

Phase 3 support: model-runner boundary without model execution.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local non-executing review runner stub under `tools/hermes_core/**`.
2. Accept only verified review session envelopes.
3. Return a pending result instead of invoking models.
4. Add focused tests for pending result, tamper rejection, and loaded-envelope input.
5. Document the runner boundary under `docs/architecture/**`.

This approval does not authorize model execution, reviewer orchestration, consensus, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for review runner boundary behavior.
- Add documentation updates that explain runner boundary behavior.
- Use local-only test fixtures and temporary files under `tests/hermes_core/**`.

## Prohibited Operations

- Do not modify `app.py`.
- Do not publish, schedule, upload, or post social content.
- Do not connect new external services.
- Do not enable autonomous workflows.
- Do not grant model agents execution authority.
- Do not add browser automation.
- Do not call model APIs or local model servers.
- Do not write secrets or credentials into repository files.
- Do not delete existing files.

## Permitted Write Paths

- `docs/architecture/**`
- `tools/hermes_core/**`
- `tests/hermes_core/**`

## Network Policy

No network access required.

## Required Exit Criteria

- Verified session envelope returns pending model-runner status.
- Tampered session envelope fails.
- Loaded envelope objects are accepted.
- Tests run locally and pass.
