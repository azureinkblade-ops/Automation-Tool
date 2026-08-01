---
title: "AUTH-2026-08-01 Hermes Ledger and Artifact Registry"
document_id: "AUTH-2026-08-01-HERMES-LEDGER-REGISTRY"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Ledger and Artifact Registry

## Authorization summary

David authorized the next implementation step after completion of the Hermes Core validator.

This authorization permits work on the local Hermes event ledger and artifact registry only.

## Parent implementation basis

Completed implementation:

- Commit `a9bef57`: Add Hermes core validator.
- `tools/hermes_core/schemas.py`
- `tools/hermes_core/state_machine.py`
- `tests/hermes_core/test_state_machine.py`
- `docs/architecture/hermes-core-validator.md`

Verification completed:

- 9 governance schemas load successfully.
- The state validator rejects prohibited transitions.
- Reviewer records cannot modify governance state.
- Acceptance records cannot authorize execution.
- Authorization artifacts must reference parent acceptance hashes.
- Targeted Hermes Core validator tests pass.

## Authorized phase

Phase 1 continuation: deterministic Hermes core.

## Active next-step approval

Status: approved to proceed.

Approved on: 2026-08-01.

Reaffirmed on: 2026-08-01.

Reaffirmation note: David re-authorized the next implementation step before ledger and registry code was created. This confirms permission to begin the scoped Hermes ledger and artifact registry work listed below and does not expand the allowed scope.

Authorized next steps:

1. Add a local append-only event ledger under `tools/hermes_core/**`.
2. Add an artifact registry that records artifact path, digest, schema name, and metadata.
3. Add deterministic SHA-256 helpers for payloads and file artifacts.
4. Add tests proving ledger append behavior, replay behavior, and tamper detection.
5. Add tests proving artifact records can be registered and verified.
6. Document the ledger and registry contract under `docs/architecture/**`.

This approval does not authorize execution workers or external integrations.

## Allowed operations

- Add focused Hermes governance core modules.
- Add local tests for event ledger and artifact registry behavior.
- Add deterministic hashing and verification helpers.
- Add read-only documentation updates that explain ledger and registry behavior.
- Use local-only test fixtures and temporary files under `tests/hermes_core/**`.

## Prohibited operations

- Do not modify `app.py`.
- Do not publish, schedule, upload, or post social content.
- Do not connect new external services.
- Do not enable autonomous workflows.
- Do not grant model agents execution authority.
- Do not add browser automation.
- Do not write secrets or credentials into repository files.
- Do not delete existing files.

## Permitted read paths

- `docs/architecture/**`
- `.hermes/**`
- `tools/hermes_core/**`
- `tests/hermes_core/**`
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

- Ledger entries are append-only at the API level.
- Ledger replay returns deterministic ordering.
- Ledger verification detects payload or digest mismatch.
- Artifact registry records include artifact identity, path, digest, schema name, and timestamp.
- Artifact verification detects missing or modified files.
- Tests run locally and pass.

## Notes

This authorization does not authorize later phases such as reviewer orchestration, worker execution, Anytype projection, Obsidian adapter writes, Codex handoff, publishing automation, or social-media workflows.
