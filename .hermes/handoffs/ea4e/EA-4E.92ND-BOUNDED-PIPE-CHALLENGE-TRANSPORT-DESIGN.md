# EA-4E.92ND bounded pipe-challenge transport design

Status: NON-LIVE DESIGN / NO NATIVE CHALLENGE PROVIDER / PRODUCTION HOLD.
Parent: `96e79876706c6e201a9fbc9960b8cb73d8119071`.

92NC requires a separate challenge observation before a retained app-instance
receipt can resolve live. The existing 92LG/92LJ/92NB pipe-client observers
can compare process and token identity, but no native component reads a
bounded ceremony challenge from a protected pipe and returns that result.

On this Windows host, an inert `NamedPipeServerStream` in byte mode reported
`CanTimeout=False`; setting `ReadTimeout=1000` threw before any connection.
This is not a safe primitive for a deadline-bound challenge read. Microsoft
documents that synchronous named-pipe I/O can block indefinitely and that
overlapped pipe I/O needs a valid `OVERLAPPED` structure and event. A canceled
operation's completion must be observed before its buffers or structure are
released or reused. Sources:

- https://learn.microsoft.com/en-us/windows/win32/ipc/synchronous-and-overlapped-input-and-output
- https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex
- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-impersonatenamedpipeclient

Next non-live implementation must use a protected, local-only, single-instance
pipe created by the independent issuer with reviewed owner, DACL, integrity
label, remote-client rejection, and readback. It must bound connect and read
deadlines, frame size, and one attempt; use overlapped I/O with exact-handle
cancellation and observed completion; prevent concurrent/interleaved reads;
compare an issuer-owned challenge and ceremony identifier with the received
canonical frame; and run client process/token observation against the same
connection after its final read. It must recheck the retained app handle,
package, and process identity before producing a non-authorizing observation.
Timeout, disconnect, partial frame, cancellation uncertainty, extra bytes,
wrong nonce, wrong ceremony, wrong client, or cleanup uncertainty deny and
require reconciliation. Never promote a caller-supplied PID or payload
`verified` field to authority.

This document does not implement, install, or run that pipe. 92NC remains
fake-only. A later native test needs exact reviewed binary/source hashes,
bounded inert client and timeout, and exact-object cleanup before a protected
issuer can be considered. No app/receiver/model, Docker mutation, GPU/ComfyUI,
or production activation occurred. Strict 92AT exact mapped-byte proof
remains REJECT/HOLD; accepted 92DE local-container provenance is separate.
