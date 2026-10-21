# EA-4E.92PW Unwired One-Attempt Owner

This source-only candidate binds one `CreateDirectory2W` invocation within one
method call to the returned native handle. It captures last-error immediately,
rejects both documented failure sentinels, owns a non-sentinel handle, checks
directory shape and descriptor on that same handle, and returns the handle to
its caller only after both readbacks. A denied path disposes the owned handle.
No production caller invokes the method. The pre-call test fixture only calls
`ScreenInputs`; it never invokes the native export.

The input screen pins the reviewed access, no-delete share, redirect flag,
and descriptor structure. It does **not** authenticate the ProgramData parent,
manifest, app SID, persistent-ACL volume, issuer token/privilege, or absence of
the first child. It does not prove effective client rights, durable one-use
semantics across calls or restarts, nor the behavior of the native export on
this host. A failed or uncertain native result must not be retried, adopted by
path, or cleaned up through this candidate. Any future native attempt needs an
independent review and its own exact bounded authorization.

Verification before staging: all 52 `Ea4e*.cs` candidate sources compiled as
a library; focused inert/ABI tests 8/8; adjacent unique non-live tests 77/77.
No native directory, receiver, model, Docker mutation, GPU, ComfyUI, or
production action occurred. The strict 92AT mapped-byte gate remains REJECT;
the local-container profile and production gates remain HOLD.
