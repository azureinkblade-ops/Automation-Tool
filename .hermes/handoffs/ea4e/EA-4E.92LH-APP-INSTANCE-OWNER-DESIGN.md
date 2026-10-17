# EA-4E.92LH app-instance owner design

Status: NON-LIVE DESIGN / NO LAUNCHER OR ISSUER IMPLEMENTED.
Baseline: `cf3b1a9c26f49c8c4e1caabdeef1fd60c9b854ed`.

## Observed integration boundary

`app.py` starts its local HTTP server in `main()` and has no protected
launcher that owns a durable process handle. EA-4E.92LG compares a connected
pipe client with a retained process object, but its caller is not an
independent owner. Reading a PID from the app's request, looking up a PID
at ceremony time, or hashing only `python.exe` cannot establish which
Python application is running. A current shell launch remains outside this
candidate authority path.

## Candidate owner

A separately installed, operator-controlled launcher must receive an
exact approved application package and dependency closure, verify their
retained object identities and bytes in the protected location, start one
ordinary-token app process with a bounded environment, and retain the
created process handle from launch until the issuer decision ends. The
launcher, not app text or a PID lookup, supplies that handle and a unique
instance nonce to the protected pipe server. No other process, reloader,
child, or restarted app automatically inherits its identity. On process
exit, owner restart, handle loss, package drift, or nonce mismatch, the
instance authority expires and the pipe check denies.

The app may send only a challenge response over the local pipe. The server
must read it on the same thread as `ImpersonateNamedPipeClient`, compare the
pipe's kernel-reported client process with the retained handle, inspect the
actual client token, and bind the response to the issuer-owned nonce and
ceremony. The payload is never an approval witness. The protected server
still needs an explicit restrictive pipe DACL, remote-client rejection,
bounded reads and connection lifetime, token duplication for read-only
`AccessCheck`, and fail-closed revert. Operator approval, byte review,
durable store, and one-action accounting are separate gates.

## Qualification and stop state

Fake-only tests should cover one matching launched instance and denials for
wrong PID, reloader/child, exited process, stale handle, restart, repeated
nonce, wrong challenge, package drift, and app-supplied PID/handle claims.
A later bounded native test must verify the real launcher-created process
handle and pipe behavior. Source review and fake tests alone cannot qualify
the protected installation, app package closure, or production activation.

This document does not start the app, install a launcher, open a pipe,
prompt for UAC, issue authority, mutate Docker, call Kilo/OpenCode or a
model, or alter the exact mapped-byte requirement. Production remains HOLD.
