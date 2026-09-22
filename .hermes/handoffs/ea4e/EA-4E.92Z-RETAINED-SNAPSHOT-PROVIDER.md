# EA-4E.92Z Retained Snapshot Provider

## Disposition

IMPLEMENTED / working-tree qualified / staged and committed verification pending.

This checkpoint implements the second EA-4E.92X design slice: a binding-aware,
read-only snapshot provider with injected query functions. It adds no native
function binding or direct process/resource operation.

## Contract

- The provider requires an exact durable binding and watcher-owned registry.
- It resolves only the three handles retained by that watcher instance.
- Job, process and thread queries are injected and each is called at most once.
- PID/TID and process/thread creation identities must match the binding.
- A live query always reports `owned_handles_closed=False`.
- A clean tombstone returns without querying closed handles.
- Registry observation holds the ownership lock through all three queries, so
  cleanup cannot close a handle during observation.
- Registry loss, drift, malformed query values, query errors and stale time
  produce an unknown outcome without retry or fallback lookup.

## Working-tree verification

- Focused EA-4E.92Y plus 92Z: 47 passed / 0 failed.
- Complete EA-4E.92S plus 92Y/92Z bounded gate: 683 passed / 0 failed.
- Bounded fake-only and filesystem tripwire events: 0 / 0.
- Canonical guarded Hermes Core: 4304 passed / 35 inherited failures /
  6 deselected / 104 subtests passed.
- Full-suite denied process attempts: 32; filesystem tripwire events: 0.
- Added and missing failure identities versus accepted EA-4E.92Y: 0 / 0.
- JUnit SHA-256:
  0370249402e91e312e43f944891e8981166765cb8885a5f67e0ea902977e7cc1.
- `git diff --check` passed.

## Initial staged-export verification

- Exact staged file count: 4.
- Staged Git tree:
  b151e2454ca112f13092972606d785d8620c2e71.
- Immutable archive: `.ea4e92z-snapshot-index-a.zip`.
- Archive SHA-256:
  63d247d9920c8cd12f7774b5d6045eca98e8eee25d40490d6e123726218cae96.
- Bounded staged gate: 683 passed / 0 failed, both tripwires zero.
- Canonical staged gate: 4304 passed / 35 inherited failures /
  6 deselected / 104 subtests passed.
- Denied process attempts: 32; filesystem events: 0.
- Added/missing failure identities: 0 / 0.
- Staged JUnit SHA-256:
  68497199b3ca35aa53fe8bfaadb261fb304a3a442c35b128262e161c3d3e6206.

## Boundary

No native API call, process launch, resource cleanup, receiver/model invocation,
production activation, network, GPU or ComfyUI activity occurred. The next
design slice is an injected cleanup owner; native execution remains separately
governed.
