# EA-4E.92PO Declaration-Only Native ABI

The private `CreateDirectory2W` P/Invoke declaration follows the pinned
Microsoft five-parameter `HANDLE WINAPI` header shape, with explicit Unicode,
exact export spelling, Winapi calling convention, and last-error capture
enabled. Its fifth argument is an opaque security-attributes pointer. There
is no wrapper, call site, executable creation mode, or native invocation in
this checkpoint.

The inert fixture reflects the declaration metadata and rejects a supplied
`create` argument without executing it. Focused tests: 3 passed. Adjacent
matrix: 374 passed, 3 existing skips. All 49 `Ea4e*.cs` sources compiled
into an ignored diagnostic DLL that was not installed.

The Microsoft W/A return-value discrepancy remains relevant. The pure 92PL
screen rejects both zero and `INVALID_HANDLE_VALUE`, but is not yet wired to
this declaration. A future caller must provide pinned, non-null descriptor
bytes in a correctly sized security-attributes structure, capture last error
immediately, reject both sentinels, own only a non-sentinel handle, and obtain
retained-handle and limited-client observations. Independent ABI/security
review and exact one-shot native authorization are required before any
mutating probe. No directory, ACL, receiver/model, Docker, GPU, ComfyUI, or
production action occurred; full 92NK and strict 92AT remain HOLD/REJECT.
