# EA-4E.92RH Nemotron Capture Regression Requalification

Status: COMMITTED-TREE NON-LIVE REGRESSION PASS / LIVE HOLD.
Source commit: `202463cd2a1d4219e12f1adf760688f7a4341730`.

The 92RG command, 92RF config candidate, 92GS model binding, and 92GQ
capture-entry tests passed 107/107 from the committed tree. The run used
stage2-v2 Python, strict non-live gating, worktree-confined pytest
collection, a fresh workspace-local basetemp, and an approved filesystem
sandbox exception. A separate 92GQ-only run passed 79/79 in the same
environment. No receiver, provider, Docker, network, GPU, or ComfyUI call
occurred.

Earlier sandboxed combined runs failed when Windows denied `os.replace`
of the capture-store anchor. The focused 92RG/RF/GS tests passed 28/28 in
the sandbox. The passing external-sandbox runs narrow the failure to that
execution context, but do not establish its exact cause or erase the failed
attempts. The capture store's production suitability is not inferred from
these fake-only tests.

The trial command and config remain source candidates, not an installed
OpenCode profile. Effective merged config, credential reference, protected
one-use issuer, egress and call accounting, exact live authorization, and
a real handoff are still unqualified. Production remains HOLD.
