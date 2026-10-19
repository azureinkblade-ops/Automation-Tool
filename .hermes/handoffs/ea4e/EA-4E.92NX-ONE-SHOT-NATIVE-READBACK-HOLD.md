# EA-4E.92NX one-shot native readback hold

Status: ONE AUTHORIZED ATTEMPT CONSUMED / DENIED / NO RETRY.
Source commit: `b19fff9389fd53b41af7d65f4621c9429758b65a`.
Local executable SHA-256 immediately before launch:
`00b8ce3b747109ab98383962d7d51d3e10535bcef55204b5fbde84afd24b5c41`.
Expected operator and app SID:
`S-1-5-21-1542204473-82821690-3590615374-1001`.
Ceremony ID: `7a044e5a-255a-423e-a670-09f4cf98c676`.
UTC deadline: `2026-10-19T21:21:42Z`.

One `Start-Process -Verb RunAs` invocation returned process ID `116732`.
That process exited with code `1`. The hidden console did not preserve its
`DENY:*` output, so the stage of denial is unknown: it may have been token
qualification, privilege enablement, creation, descriptor readback, or
privilege restoration. Do not infer that an actual protected pipe was
created or that a specific native check passed. No automatic retry occurred.

After exit, process ID `116732` was absent and enumeration found zero pipes
matching the ceremony prefix. This is post-exit cleanup evidence, not proof
of the transient native path or exact handle history. Source/tests and
production state were not changed by this attempt. No client, Docker
mutation, Kilo/OpenCode receiver, model, GPU, ComfyUI, or production
activation was run.

Before any fresh native authorization, a new non-live fixture must preserve
bounded denial and cleanup diagnostics outside the hidden console, then
receive a new source commit, executable hash, reviewed invocation, deadline,
and one-attempt approval. The 92NK native gate and production readiness
remain HOLD.
