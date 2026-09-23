# EA-4E.92AC Retained Watcher Composition

## Disposition

Non-live implementation after EA-4E.92AB. This checkpoint is an additional
composition prerequisite identified by native-qualification preflight. It
does not implement a native launcher or pre-resume query adapter and does not
authorize any NQ probe.

## Contract

- Explicit composition accepts one exact already-created registry, one
  injected resource API and a monotonic clock.
- The snapshot provider, exact observer and one-shot cleanup owner share that
  same registry and the registry's immutable watcher instance identity.
- Composition itself does not register handles, load a DLL, query, terminate,
  close, discover, or launch a resource.
- A fake-only end-to-end handoff proves live observation, exact ordered
  cleanup, tombstone replay without another query, wrong-identity denial,
  lost-registry denial, and fail-closed unknown cleanup with no retry.
- No app.py route or production watcher startup constructs this composition.

## Working-tree verification

- Focused 92Y through 92AC: 83 passed / 0 failed.
- Complete EA-4E.92S through 92AC bounded gate: 719 passed / 0 failed.
- Bounded fake-only and filesystem tripwires: 0 / 0.
- Canonical guarded Hermes Core: 4,340 passed / 35 inherited failures /
  6 deselected / 104 subtests passed.
- Full-suite denied process attempts: 32; filesystem tripwire events: 0.
- Failure identities versus committed 92AB: 0 added / 0 missing.
- Canonical JUnit SHA-256:
  de4443189ab88708d881e83a93257776087e32d2accb20183375e4d3fb27e578.

## Boundary

Native launch and pre-resume verification remain absent. A real NQ-12 watcher
also requires reviewed ownership transfer and host-bound authorization. No
native API call, real process/resource cleanup, receiver/model invocation,
production activation, network, GPU or ComfyUI operation occurred. Fake tests
do not establish production readiness.
