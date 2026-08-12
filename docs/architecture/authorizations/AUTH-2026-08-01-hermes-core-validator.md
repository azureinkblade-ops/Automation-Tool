---
title: "AUTH-2026-08-01 Hermes Core Validator"
document_id: "AUTH-2026-08-01-HERMES-CORE-VALIDATOR"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Core Validator

## Authorization summary

David authorized the next implementation step after approval of ADR-0001 through ADR-0004 and completion of the architecture foundation contracts.

This authorization permits work on the Hermes Core validator only.

## Parent acceptance basis

Accepted architecture:

- ADR-0001: Hermes is the sole governance authority.
- ADR-0002: Reviewer models have review-only authority.
- ADR-0003: Acceptance is calculated by deterministic consensus.
- ADR-0004: Acceptance and execution authorization are separate.

Foundation artifacts created:

- `docs/architecture/decisions/README.md`
- `docs/architecture/state-machine.md`
- `docs/architecture/schemas/*.schema.yaml`
- `docs/architecture/README.md`

Verification completed:

- 9 schema contracts parse as YAML.
- ADR-0001 through ADR-0004 are accepted in ADR files and ADR index.
- The state machine blocks `ACCEPTED -> AUTHORIZED` and `ACCEPTED -> EXECUTING`.

## Authorized phase

Phase 1: Hermes Core validator preparation and implementation.

## Active next-step approval

Status: approved to proceed.

Approved on: 2026-08-01.

Reaffirmed on: 2026-08-01.

Reaffirmation note: David re-authorized the next implementation step before validator code was created. This confirms permission to begin the scoped Hermes Core validator work listed below and does not expand the allowed scope.

Authorized next steps:

1. Create the Hermes Core validator module scaffold under `tools/hermes_core/**`.
2. Add local tests under `tests/hermes_core/**`.
3. Implement schema loading for the accepted governance contracts.
4. Implement deterministic transition validation from `docs/architecture/state-machine.md`.
5. Prove the validator rejects direct reviewer-state changes and acceptance-to-execution shortcuts.

This approval does not expand the scope beyond the allowed and prohibited operations below.

## Allowed operations

- Add focused Hermes governance core modules.
- Add tests for schema loading and transition validation.
- Add deterministic validation for allowed and prohibited state transitions.
- Add read-only documentation updates that explain validator behavior.
- Use local-only test fixtures.

## Prohibited operations

- Do not modify `app.py`.
- Do not publish, schedule, upload, or post social content.
- Do not connect new external services.
- Do not enable autonomous workflows.
- Do not grant model agents execution authority.
- Do not write secrets or credentials into repository files.
- Do not delete existing files.

## Permitted read paths

- `docs/architecture/**`
- `.hermes/**`
- `tools/**`
- `tests/**`
- repository metadata needed for status and verification

## Permitted write paths

- `docs/architecture/**`
- `tools/hermes_core/**`
- `tests/hermes_core/**`

## Network policy

No network access required.

## Fixture policy

Local-only fixtures are allowed under `tests/hermes_core/**`.

## Required exit criteria

- Transition validator rejects prohibited shortcuts.
- Transition validator accepts documented allowed transitions only when required artifacts are present.
- Reviewer records cannot directly alter governance state.
- Acceptance records cannot authorize execution.
- Authorization records must reference parent acceptance hashes.
- Tests run locally and pass.

## Notes

This authorization does not authorize later phases such as event bus, registries, worker execution, Anytype projection, Obsidian adapter work, Codex handoff, publishing automation, or social-media workflows.
