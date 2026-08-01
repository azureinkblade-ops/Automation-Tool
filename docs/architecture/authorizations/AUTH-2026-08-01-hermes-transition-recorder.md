---
title: "AUTH-2026-08-01 Hermes Transition Recorder"
document_id: "AUTH-2026-08-01-HERMES-TRANSITION-RECORDER"
version: "0.1.0"
status: "authorized"
owner: "David Powell"
system: "Hermes"
issued_at: "2026-08-01"
expires_at: "2026-08-08"
---

# AUTH-2026-08-01 Hermes Transition Recorder

## Authorization summary

David authorized the next implementation step after completion of the Hermes Core validator, local event ledger, and artifact registry.

This authorization permits work on the local Hermes transition recorder only.

## Parent implementation basis

Completed implementation:

- Commit `a9bef57`: Add Hermes core validator.
- Commit `df22662`: Add Hermes ledger registry.
- `tools/hermes_core/state_machine.py`
- `tools/hermes_core/ledger.py`
- `tools/hermes_core/registry.py`

Verification completed:

- 17 Hermes Core tests pass.
- State transitions are validated before acceptance.
- Ledger append and replay behavior works.
- Ledger tampering is detected.
- Artifact registration and verification works.

## Authorized phase

Phase 1 continuation: deterministic Hermes core.

## Active next-step approval

Status: approved to proceed.

Approved on: 2026-08-01.

Authorized next steps:

1. Add a local transition recorder under `tools/hermes_core/**`.
2. Validate transition requests with the existing state-machine validator.
3. Write exactly one ledger event for each accepted transition.
4. Write no ledger event for rejected transitions.
5. Add replay helpers that reconstruct the latest task state from transition events.
6. Add focused tests for accepted transitions, rejected transitions, authorization hash checks, and replay behavior.
7. Document the transition recorder contract under `docs/architecture/**`.

This approval does not authorize execution workers or external integrations.

## Allowed operations

- Add focused Hermes governance core modules.
- Add local tests for transition recording and replay.
- Add read-only documentation updates that explain recorder behavior.
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

- Accepted transition writes one ledger event.
- Rejected transition writes no ledger event.
- Recorder rejects prohibited shortcuts.
- Recorder enforces authorization parent acceptance hash checks through the validator.
- Replay reconstructs latest task state from transition events.
- Tests run locally and pass.

## Notes

This authorization does not authorize later phases such as reviewer orchestration, worker execution, Anytype projection, Obsidian adapter writes, Codex handoff, publishing automation, or social-media workflows.
