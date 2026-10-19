# EA-4E.92MY issuer app-token binding design

Status: NON-LIVE DESIGN / NOT AN ISSUER / PRODUCTION HOLD.
Parent: `4a8ee049e059532d0f879b59bb3b836fd19c481e`.
Profile: accepted 92DE local-container profile only. The strict 92AT
mapped-byte requirement remains REJECT/HOLD.

## Existing pieces and mismatch

92LA's `Ea4eProtectedPathAccessCandidate` calls `OpenProcessToken` on the
current process, demands an unelevated token, duplicates it, and applies
`AccessCheck` to retained path handles. That is appropriate for its current
unelevated read-only probe. In an elevated issuer, the current process token
is the operator's elevated token, not the ordinary app token. Reusing the
method there would deny or measure the wrong principal.

92LF's `Ea4ePipeClientTokenCandidate` observes a connected named-pipe client's
limited token and SID, then disposes its handle. 92LG and 92LJ compare the
kernel-observed client process with an externally retained process handle
before and after that token observation. 92LQ's in-memory app-instance owner
is fake-collaborator-qualified; it does not create a trusted native launcher.
None of these pieces retains a bound client impersonation token through a
path-access check or supplies an independently trusted app-instance receipt.

## Narrow non-live composition to qualify

1. A separately trusted launcher owns the live app process handle, canonical
   package digest, instance nonce, PID, and lifecycle. The issuer obtains that
   receipt from a protected channel, not from the app request. The current
   92LQ object alone cannot assert this receipt.
2. A protected, local-only pipe accepts one bounded request. After a message
   read, compare the pipe's kernel-observed client process with the retained
   process object, then impersonate that same pipe client. Check SID,
   limited-token state, and impersonation level. Retain a valid duplicate
   impersonation token for the duration of the path observation and always
   revert the issuer thread, including failure paths. Recheck the client
   process object before using or publishing the observation.
3. Refactor the path-access core to accept only that internally acquired,
   retained token and bound SID. Keep the current-process wrapper for its
   unelevated probe, but do not call it from elevated issuance. Evaluate
   owner and effective mutation rights on every retained ancestor/closure
   handle; pair this with the existing handle-bound byte snapshot. A free
   `verified=true` or caller-supplied token-handle parameter must not become
   an issuer authority input.
4. Bind the pipe transaction to the exact app-instance receipt, protected
   policy hash, governing commit, authority/attempt/request identity, and
   one-use ceremony nonce. A stale, replayed, disconnected, substituted, or
   concurrently changed client denies. The issuer must acquire independent
   policy, store, clock, Docker, and operator observations before a v5 claim.
5. The protected pipe's owner, effective DACL, integrity label, local-only
   transport, and creation semantics require their own installed-fixture
   qualification. 92LN is a readback candidate, not proof of installation.

Negative tests must cover elevated issuer versus unelevated app token,
wrong/SYSTEM SID, elevated client, changed client process, duplicate message,
closed token or pipe, failed impersonation/revert, writable ancestor, reparse
swap, altered installed byte, expired nonce, and unavailable trusted receipt.
Positive fake/native tests can establish observation composition only; they
cannot substitute for a protected install or independent operator review.

Current-tree adjacent gate: 53 passed and 14 failed under the filesystem
sandbox. Every failure stopped at `PIPE_CONNECTION_FAILED` or
`PIPE_CONNECTION_UNAVAILABLE`, before the candidate token/process comparison.
The exact 92LF/92LG/92LJ subset then passed 14/14 in a permitted native
rerun outside that sandbox. This classifies the first run as a pipe-access
environment limitation, not a production qualification or a code fix.

No source change, privileged helper build or launch, UAC prompt, protected
installation, Docker mutation, Kilo/OpenCode/model call, GPU/ComfyUI activity,
or production activation is authorized or performed by this design.
