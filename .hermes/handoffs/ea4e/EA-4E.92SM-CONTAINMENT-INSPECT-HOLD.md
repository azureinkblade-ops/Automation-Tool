# EA-4E.92SM containment inspect HOLD

Date: 2026-10-26

The user authorized exactly one tags-only native test of the empty
`manifests-v2` hypothesis at source commit
`61cf28b1f12464acdde2e1767e3670d2bfacb2fb`. Before invocation, the
tracked tree was clean, the entrypoint, parser, and Docker CLI SHA-256 values
matched the authorization, the six pinned model files validated, the new
directory was empty, and no prior `ea4e92rm-` container existed.

The single invocation failed at the first effective-container inspection:
`SmokeDenied: effective container containment mismatch`. The launcher did
not start Ollama or send `/api/tags`; no inference, receiver, agent handoff,
GPU assignment, or production activation occurred. Its exact-owned cleanup
completed. A separate read-only Docker query found no remaining
`ea4e92rm-` container. The one-shot authorization is consumed. There was no
retry.

The current verification combines many Docker inspect predicates into one
fail-closed result, and the container was already removed, so the differing
field is not known. The empty-v2-root hypothesis remains untested. Next:
develop a bounded, non-sensitive mismatch classifier and focused fake tests;
obtain independent source-only review before requesting any new exact native
authorization. Do not weaken containment predicates based on speculation.
Production remains HOLD.
