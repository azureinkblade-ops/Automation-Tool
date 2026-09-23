# EA-4E.92AB Lazy Windows Retained-Handle Binding

## Disposition

Non-live implementation of EA-4E.92X slice 4. Native qualification remains
separately governed and is not authorized by this artifact.

## Contract

- Importing the adapter does not load a DLL or bind a native function.
- Explicit construction binds eight reviewed kernel32 signatures. Fake
  qualification supplies a fake DLL; no real kernel32 function is called.
- Only already-retained handles are accepted by query and cleanup methods.
  The adapter cannot open a PID/TID or create a process, job, or thread.
- Process/thread identity comes from the exact handle, creation FILETIME, and
  zero-timeout signaled-state query. Unexpected wait results fail closed.
- Job active count comes from basic accounting information on the exact job
  handle. Termination and close methods expose the existing cleanup-owner
  injection contract; they are not wired into a running watcher.
- No retry, fallback, PID reopen, durable raw-handle write, or implicit
  production activation is provided.

## Working-tree verification

- Focused 92Y/92Z/92AA/92AB: 77 passed / 0 failed.
- Complete EA-4E.92S through 92AB bounded gate: 713 passed / 0 failed.
- Bounded fake-only and filesystem tripwires: 0 / 0.
- Canonical guarded Hermes Core: 4,334 passed / 35 inherited failures /
  6 deselected / 104 subtests passed.
- Full-suite denied process attempts: 32; filesystem tripwire events: 0.
- Failure identities versus committed 92AA: 0 added / 0 missing.
- Canonical JUnit SHA-256:
  36a6b0089e1d48f505a0a46b9ef8f22ee426418819efea115f9b8e85c4df00ad.

## Boundary

No native API call, process/resource operation, receiver/model invocation,
production activation, network, GPU or ComfyUI activity occurred. Before any
real watcher wiring or native qualification, separately review the exact
retained-handle rights, live binding lifetime, termination scope and bounded
native authorization. Fake-only tests do not establish production readiness.
