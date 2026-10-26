# EA-4E.92SZ startup-log review correction

Date: 2026-10-26

The one approved independent read-only review of pinned startup-log
candidate `cc986d6eaddf5fda43327239e0f94cfe0e7b0f19` returned source
HOLD. The reviewer found that a process exit during `/api/tags`, after a
successful interface check, could bypass the bounded startup-category
classifier and yield only a generic Docker command failure. The reviewer
made no edits, tests, Docker, Ollama, model, GPU, receiver, or handoff
calls. The one-review approval is consumed.

The source-only successor adds one exact-owned, full-containment state
recheck on a tags-request denial in diagnostic mode. A stopped process
uses the same bounded exit/OOM and fixed startup-category path; a running
process preserves its original safe denial. The ordinary no-logging tags
path is unchanged. A fake regression covers an exit during `/api/tags`,
one bounded log read, no generate request, and exact cleanup. Focused
strict non-live tests passed 63/63. No native run followed the finding.

The corrected committed blob needs a new independent source-only review.
Any live use still requires separate exact one-shot authorization that
explicitly accepts transient daemon-local logging. Docker's requested
one-file 16 KiB cap is not proof of a hard disk-usage bound or forensic
zero-retention. Production remains HOLD.
