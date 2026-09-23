# EA-4E.92AA Injected Cleanup Owner

## Disposition

IMPLEMENTED / working-tree qualified / staged and committed verification pending.

This checkpoint implements the third EA-4E.92X design slice. Cleanup functions
and resource queries are injected. The production modules bind no native
function and perform no direct process or resource operation.

## Contract

- The exact watcher binding and retained handles are resolved under one lock.
- Initial queries verify PID/TID and creation identities before termination.
- Exactly one injected job-termination call precedes final state queries.
- Final queries must show zero active owned processes and process/thread absence.
- The exact injected close order is thread, process, job; each must return `True`.
- A monotonic cleanup observation follows the close operations.
- Only then does the registry atomically replace handle resolution with an
  immutable clean tombstone.
- Exact clean replay returns the tombstone without repeating operations.
- Any failure marks the in-memory cleanup outcome unknown and blocks
  registration replay, handle resolution, another cleanup attempt and a clean
  tombstone claim.
- The same lock serializes read-only observation and cleanup.

## Working-tree verification

- Focused 92Y/92Z/92AA: 65 passed / 0 failed.
- Complete EA-4E.92S through 92AA bounded gate: 701 passed / 0 failed.
- Bounded fake-only and filesystem tripwire events: 0 / 0.
- Canonical guarded Hermes Core: 4322 passed / 35 inherited failures /
  6 deselected / 104 subtests passed.
- Full-suite denied process attempts: 32; filesystem tripwire events: 0.
- Added and missing failure identities versus accepted 92Z: 0 / 0.
- JUnit SHA-256:
  7a4b0290f96fa311b43b040001192b9d78ba10ba211fdf7949a238d6925c919a.
- `git diff --check` passed.

## Initial staged-export verification

- Exact staged file count: 5.
- Staged Git tree:
  32fbd83766a188de3000e34591c9b04c46c6893d.
- Immutable archive: `.ea4e92aa-cleanup-index-a.zip`.
- Archive SHA-256:
  e6bc5d38f5dfea1c7c4d35b1be8ddc95f880ae0962eb63bebc47ef3ffc26baa5.
- Bounded staged gate: 701 passed / 0 failed, both tripwires zero.
- The first full staged process ended without a report at 66%.
- A fresh isolated canonical rerun completed: 4322 passed / 35 inherited
  failures / 6 deselected / 104 subtests passed.
- Denied process attempts: 32; filesystem events: 0.
- Added/missing failure identities: 0 / 0.
- Completed staged JUnit SHA-256:
  8944cc8ac7a433a36b18c27fbe2c99937ba77195b230a21f6126a37edbc2d626.

## Boundary

No native API call, real process/resource cleanup, receiver/model invocation,
production activation, network, GPU or ComfyUI activity occurred. The next
non-live slice is lazy explicit Windows function binding with fake-only tests.
Any native qualification requires separate bounded authorization.
