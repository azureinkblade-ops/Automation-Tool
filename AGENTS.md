# AGENTS.md

Repository rules for any AI coding session working in this repo. These are
authoritative for `app.py` and cross-session coordination. (Behavioral coding
guidelines live in `CLAUDE.md`; this file governs multi-session coordination.)

## app.py Coordination Rule

`app.py` is a shared monolith and may have only one active implementation
writer at a time.

Before another session begins modifying `app.py`, the current writer must:

1. Finish and commit its changes, or stash them explicitly.
2. Confirm the working tree state.
3. Push the commit when the work is intended to be shared.
4. Provide the receiving session with the commit hash and affected regions.
5. Declare the handoff complete.

The receiving session must:

1. Pull or inspect the handoff commit before editing.
2. Confirm that the working tree is clean.
3. Re-read the intended call sites before applying changes.
4. Avoid broad formatting or unrelated cleanup in `app.py`.
5. Commit the assigned change as an isolated unit.

Do not run two concurrent uncommitted edit lanes against `app.py`.

Isolated modules outside `app.py` may be developed concurrently when they
have explicit interfaces and do not modify the same files.

## Current lane ownership

- Video/TTS and live `app.py` pipeline integration:
  editing session `20260715_060146_c55923`

- AIVSB reasoning, Studio Bible architecture, retrieval, Prompt Composer,
  and strategy:
  reasoning/strategy session

Any transfer of `app.py` ownership requires an explicit handoff.

## Active handoffs

- **Phase C — connect `compose_aivsb_scene_prompt()` to
  `make_chapter_image_prompts()`.** Owner: editing session
  `20260715_060146_c55923`. Brief:
  `.hermes/handoffs/PHASE-C-aivsb-reasoning-integration.md`.
