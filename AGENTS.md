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

## Team Gateway Checklist (hardened handoff gates)

Adapted from Ruflo's Team Gateway Checklist (MIT, `ruvnet/ruflo`) as stricter,
explicit gates on top of the 5-step handoff above. These are mandatory for any
`app.py` ownership transfer. Borrowed as patterns only; Ruflo is not installed
and no Automation Tool traffic routes through it.

Before a handoff commit is considered complete (before-merge gates):

1. **Dual-mode handoff.** The writer records both the intent (what changed and
   why) and the diff regions, so the receiver can act without re-deriving
   context. Partial handoffs are not valid transfers.
2. **Per-merge witness.** Record the commit hash, affected files, and a short
   signature of the change (what it must and must not alter) in the handoff
   note under `.hermes/handoffs/`. A merge without a corresponding handoff
   entry is rejected.
3. **Namespace isolation.** Concurrent work outside `app.py` must not share
   mutable state with the monolith lane. Shared files require an explicit
   interface contract in the handoff note.
4. **No broad cleanup in transit.** Formatting, import reordering, or
   unrelated refactors are not part of a handoff and must be their own isolated
   commits after the transfer, never bundled with the functional change.
5. **Verification before declare.** The writer confirms the change passes its
   own guard (regression smoke, build) before declaring the handoff complete.
   The receiver re-confirms a clean tree before the first edit.

Em-dash rule (tooling constraint, not just style): commit messages, file/path
names, and any value passed to CLI tooling must not contain em dashes. Ruflo's
own `memoryStore` broke on em-dash titles because npm rejects arguments
starting with a non-ASCII dash. Azure Inkblade external copy also forbids em
dashes (brand rule). Keep em dashes out of machine-parsed strings.

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
