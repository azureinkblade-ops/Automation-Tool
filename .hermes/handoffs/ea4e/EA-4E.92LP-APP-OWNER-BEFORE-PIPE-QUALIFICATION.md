# EA-4E.92LP app-owner sequencing review

Status: NON-LIVE SOURCE/PROCESS INVENTORY / PRODUCTION HOLD.
Baseline: `0bb59b6d82916f7b839c25bcdc4431113482a613`.

The `app.py` entry point calls `main()` directly and starts a
`ThreadingHTTPServer` on loopback. It does not return a retained process
handle, instance nonce, or approved package identity to a separate
operator-controlled owner. This is the open 92LH boundary; the read-only
92LG/92LJ process match expects a handle but cannot manufacture its
provenance.

A read-only Windows process inventory on 2026-10-17 found two `app.py`
command-line candidates. One was the other's parent. Their executable
paths resolved to the Automation Tool `.venv-gpu` Python and a Codex
runtime Python respectively. This inventory was obtained outside the
Codex filesystem sandbox because the sandboxed CIM query was denied.
The earlier sandbox query's apparent zero count was an error artifact,
not evidence that no app was running. No process was opened, stopped,
restarted, or adopted as authoritative. PIDs and start times are ephemeral
and are intentionally not frozen as an app-instance identity.

Ordering consequence:

1. Build and fake-test the independent, operator-controlled app-instance
   owner defined in 92LH. It must retain the handle returned by its own
   launch, bind an exact reviewed package/dependency closure and instance
   nonce, and invalidate on exit, restart, reloader/child substitution,
   package drift, or owner restart. It must not adopt a discovered PID.
2. Prepare and source-review a temporary protected-pipe access probe for
   the same-account UAC case. A dummy limited-token client can qualify
   DACL, owner-rights, and mandatory-label behavior, but cannot prove the
   real app-instance handoff.
3. Only a later bounded native test may combine the retained app handle,
   real app token, 92LJ client process/token observation, pipe owner/DACL/
   label readback, and challenge protocol. This needs its own exact
   authorization, binary/source hashes, one-attempt budget, timeout, and
   exact-object cleanup before any issuer or receiver authority is used.

No code or tests were changed in this checkpoint. The process inventory
does not authorize launching the app, prompting for UAC, creating a pipe,
issuing authority, mutating Docker, invoking Kilo/OpenCode or a model, or
activating production. The local-container provenance alternative does not
remove this app-instance authority requirement. Production remains HOLD.
