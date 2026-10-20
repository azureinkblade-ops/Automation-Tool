# EA-4E.92OK inert announcement lease

Status: NON-LIVE FAKE-ONLY / NO NATIVE FILE OR PIPE.
Governing parent: `8830d4b370ae9003f7e7dfe0f46c159d31ae45af`.

`tools/ea4e92ok_announcement_lease.py` wraps the 92OJ canonical record
validator with a process-local, one-use state transition. Only an explicitly
fake-only instance can be created. The first consume attempt moves to UNKNOWN
before validation; a malformed first record cannot be retried with a valid
record. One valid consume moves to CONSUMED and any replay is denied. Close is
terminal. The fixture does not expose a native mode.

This is not durable replay prevention. A restarted process could construct a
new fake lease, and a matching JSON record does not prove its file handle,
namespace ACL, creator process, or pipe identity. The accepted 92DE profile
does not convert this fake accounting into an issuer. The next gate remains
trusted installed namespace and retained-handle observation, with persistent
one-shot state bound to the ceremony. No native file, pipe, Docker mutation,
Kilo/OpenCode receiver, model, GPU, ComfyUI, or production activation occurred.

Dedicated fake tests: 7/7. Staged-byte and committed-tree results are recorded
with the checkpoint completion.
