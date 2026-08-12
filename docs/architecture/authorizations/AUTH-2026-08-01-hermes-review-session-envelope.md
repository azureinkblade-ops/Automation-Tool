---
title: "AUTH-2026-08-01 Hermes Review Session Envelope"
document_id: "AUTH-2026-08-01-HERMES-REVIEW-SESSION-ENVELOPE"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Review Session Envelope

## Authorization Summary

David authorized continuing the Hermes agent-to-agent governance rebuild after the review assignment builder.

This authorization permits a local read-only review session envelope builder only.

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
- `tools/hermes_core/review_assignment.py`
- `tools/hermes_core/hashing.py`

Verification completed:

- 57 Hermes Core tests pass.
- Review assignment builder creates deterministic plans for eligible evidence and active reviewers.

## Authorized Phase

Phase 3 support: frozen review session input packages.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local review session envelope builder under `tools/hermes_core/**`.
2. Freeze ready assignment plans into read-only JSON documents.
3. Hash the session envelope for tamper detection.
4. Add focused tests for build, freeze, unready plans, tampering, and read-only enforcement.
5. Document the envelope contract under `docs/architecture/**`.

This approval does not authorize model execution, reviewer orchestration, consensus, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for review session envelope behavior.
- Add documentation updates that explain envelope behavior.
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

- Ready assignment plans build verifiable session envelopes.
- Session envelopes can be frozen to file and verified.
- Unready plans fail.
- Tampered envelopes fail.
- Non-read-only envelopes fail.
- Tests run locally and pass.
