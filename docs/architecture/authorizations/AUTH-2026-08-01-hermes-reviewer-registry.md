---
title: "AUTH-2026-08-01 Hermes Reviewer Registry"
document_id: "AUTH-2026-08-01-HERMES-REVIEWER-REGISTRY"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Reviewer Registry

## Authorization Summary

David authorized continuing the Hermes agent-to-agent governance rebuild after the review report validator.

This authorization permits a local reviewer registry only.

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
- `docs/architecture/schemas/agent.schema.yaml`

Verification completed:

- 45 Hermes Core tests pass.
- Review report validation blocks mismatched evidence, unknown references, duplicate findings, missing recommendations, invalid timing, and authority claims.

## Authorized Phase

Phase 3 support: reviewer identity and authority registration.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local reviewer registry under `tools/hermes_core/**`.
2. Validate reviewer records against `hermes.agent`.
3. Enforce reviewer-only authority limits.
4. Reject duplicate reviewer identities.
5. Expose active reviewer lookup and minimum count checks.
6. Add focused tests for valid reviewers, duplicate ids, wrong roles, authority claims, and insufficient active reviewers.
7. Document the registry contract under `docs/architecture/**`.

This approval does not authorize model execution, reviewer orchestration, consensus, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for reviewer registry behavior.
- Add documentation updates that explain registry behavior.
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

- Valid reviewer records load.
- Duplicate reviewer ids fail.
- Non-reviewer roles fail.
- Execution and governance authority claims fail.
- Minimum active reviewer count check works.
- Tests run locally and pass.
