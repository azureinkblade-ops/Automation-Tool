---
title: "AUTH-2026-08-01 Hermes Review Assignment Builder"
document_id: "AUTH-2026-08-01-HERMES-REVIEW-ASSIGNMENT-BUILDER"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Review Assignment Builder

## Authorization Summary

David authorized continuing the Hermes agent-to-agent governance rebuild after the reviewer registry.

This authorization permits a local review assignment builder only.

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
- `tools/hermes_core/review_gate.py`
- `tools/hermes_core/reviewer_registry.py`

Verification completed:

- 52 Hermes Core tests pass.
- Reviewer registry enforces reviewer-only authority and active reviewer lookup.

## Authorized Phase

Phase 3 support: read-only review assignment planning.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local review assignment builder under `tools/hermes_core/**`.
2. Use the review eligibility gate before assigning reviewers.
3. Use the reviewer registry for active reviewer selection.
4. Return a structured plan without launching models.
5. Add focused tests for ready plans, stale evidence, too few reviewers, custom roles, and unknown roles.
6. Document the assignment builder contract under `docs/architecture/**`.

This approval does not authorize model execution, reviewer orchestration, consensus, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for review assignment behavior.
- Add documentation updates that explain assignment behavior.
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

- Clean eligible evidence with enough active reviewers creates assignments.
- Stale evidence blocks assignments.
- Too few active reviewers blocks assignments.
- Custom review roles are applied deterministically.
- Unknown review roles fail.
- Tests run locally and pass.
