---
title: "AUTH-2026-08-01 Hermes Evidence Package Builder"
document_id: "AUTH-2026-08-01-HERMES-EVIDENCE-PACKAGE-BUILDER"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Evidence Package Builder

## Authorization Summary

David authorized the next implementation step after completion of the Hermes transition recorder.

This authorization permits work on the local Hermes evidence package builder only.

## Parent Implementation Basis

Completed implementation:

- Commit `a9bef57`: Add Hermes core validator.
- Commit `df22662`: Add Hermes ledger registry.
- Commit `f96f423`: Add Hermes transition recorder.
- `tools/hermes_core/state_machine.py`
- `tools/hermes_core/ledger.py`
- `tools/hermes_core/registry.py`
- `tools/hermes_core/transition_recorder.py`

Verification completed:

- 21 Hermes Core tests pass.
- Accepted transitions write one ledger event.
- Rejected transitions write no ledger event.
- Replay reconstructs latest task state.

## Authorized Phase

Phase 2 start: evidence package system.

## Active Next-Step Approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local evidence package builder under `tools/hermes_core/**`.
2. Inventory local artifacts by path, artifact id, artifact type, and SHA-256.
3. Produce a frozen evidence package document that validates against `hermes.evidence`.
4. Write the package to disk using canonical JSON.
5. Verify that package hash and artifact hashes still match.
6. Reject missing artifacts.
7. Add focused tests for package creation, schema validation, missing artifact rejection, and mutation detection.
8. Document the evidence package builder contract under `docs/architecture/**`.

This approval does not authorize reviewer orchestration, model execution, browser automation, posting workflows, or external integrations.

## Allowed Operations

- Add focused Hermes governance core modules.
- Add local tests for evidence package creation and verification.
- Add documentation updates that explain evidence package behavior.
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

## Permitted Read Paths

- `docs/architecture/**`
- `.hermes/**`
- `tools/hermes_core/**`
- `tests/hermes_core/**`
- repository metadata needed for status and verification

## Permitted Write Paths

- `docs/architecture/**`
- `tools/hermes_core/**`
- `tests/hermes_core/**`

## Network Policy

No network access required.

## Fixture Policy

Local-only fixtures are allowed under `tests/hermes_core/**`.

## Required Exit Criteria

- Evidence package creation succeeds for existing files.
- Evidence package document validates against `hermes.evidence`.
- Missing artifacts are rejected.
- Mutating an inventoried artifact invalidates verification.
- Mutating the package document invalidates verification.
- Tests run locally and pass.

