# EA-4E.92SE tags-only diagnostic candidate

Date: 2026-10-26

The single authorized 92SD local-model smoke stopped on an invalid local
`/api/tags` HTTP response before inference. Its authorization was consumed.
The 92SD diagnostic successor can now report status, JSON content-type
match, and body byte count without exposing body content.

This candidate adds a fixed tags-only entrypoint. It reuses the pinned image,
Docker CLI hash, staged model root, containment checks, 90-second work and
best-effort 120-second wall budget, and exact-owned-container cleanup from
the existing launcher. After validating a pinned model in `/api/tags`, it
returns without constructing or sending `/api/generate`. There is no cloud,
receiver, agent-handoff, GPU assignment, or production activation path.

The focused strict non-live suite passed 31/31, including tests that the
tags-only path issues exactly one tags request, issues no generate request,
and cleans up its fake owned container. These are fake tests, not native
qualification. Independent source review and a new exact one-shot native
authorization are required before executing this diagnostic. Production
remains HOLD.
