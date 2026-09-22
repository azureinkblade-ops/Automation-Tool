# EA-4E.92W Durable Observer-Binding Enforcement

## Disposition

IMPLEMENTED / staged-export qualified / not committed / not pushed.

This non-live checkpoint closes the integration gap between the schema-v2
NQ-12 observer binding and the existing reconciliation/observer path. It adds no
native provider, native API call, process operation, cleanup authority,
receiver/model invocation, production activation, network, GPU or ComfyUI
capability.

## Governing state

- Branch: feature/ea4e67-kilo762-roll
- Synchronized parent: 4b7eb8050a24aa45df883839fbf4fb40ff23e8b3
- Tracked unstaged state at start: clean
- Staged state at start: clean

## Defect

The durable store already required a schema-v2 `ObserverResourceBinding`, but
`reconcile_broker_death()` did not require or load it. The controller passed
only process-local job/process/thread integers to the observer, and the observer
could call a future provider without proving that the caller's expected watcher
instance and opaque retained-resource tokens matched the durable record.

That gap made it unsafe to implement the native provider: bare PID/TID values
can be reused and a job-handle integer is not a cross-process durable identity.

## Correction

- `reconcile_broker_death()` now requires an explicit observer instance ID.
- An UNKNOWN NQ-12 record must have an exact durable observer binding before the
  observer can be called.
- Missing, malformed, tampered or wrong-watcher bindings fail closed before any
  observer/provider operation.
- The exact validated binding is passed through the observer boundary.
- `ExactOwnedResourceObserver` independently validates that binding against its
  configured watcher identity and the durable PID/TID before one provider call.
- The provider protocol now receives the opaque binding needed to resolve a
  future exact retained-handle registry; it cannot be driven by bare IDs alone.
- Clean reconciliation replay remains observer-free and idempotent.

## Verification

Focused identity/store/observer/controller gate:

- 93 passed / 0 failed
- fake-only process/network tripwire events: 0
- filesystem tripwire events: 0

Complete EA-4E.92S bounded gate:

- 636 passed / 0 failed
- fake-only process/network tripwire events: 0
- filesystem tripwire events: 0

Canonical guarded Hermes Core gate:

- 4257 passed
- 35 inherited failures
- 6 explicitly deselected OS-process tests
- 104 subtests passed
- denied process attempts: 32
- filesystem tripwire events: 0
- added failure identities versus accepted EA-4E.92V baseline: 0
- missing failure identities versus accepted EA-4E.92V baseline: 0
- JUnit SHA-256:
  991243625d307d33753f68633c182034b71ae0493df3aac30ea3bd0716d6c44f

`git diff --check` passed. The production modules still contain no subprocess,
shell, native DLL, process launch/resume, network, browser, receiver/model, GPU
or ComfyUI capability.

## Initial staged-export verification

- Exact staged file count: 5
- Staged Git tree:
  fdf37c6637c97deeb27de752bdecd0f1c400f415
- Immutable archive:
  .ea4e92w-binding-enforcement-index-a.zip
- Archive SHA-256:
  f9c0ae20a61a539a0bc938e16ef159aef6e26f678888b5c76ba34496d43b87b2
- Complete staged EA-4E.92S bounded gate: 636 passed / 0 failed
- Staged canonical Hermes Core gate: 4257 passed / 35 inherited failures /
  6 deselected / 104 subtests passed
- denied process attempts: 32
- filesystem tripwire events: 0
- added/missing failure identities: 0 / 0
- staged JUnit SHA-256:
  e3e4998c473e021018e90e1d7f5b0a711dc38209aa2f2553caf4e950a64a500b

## Boundary

- Native retained-handle registry/provider: not implemented.
- Native observer/probe execution: not authorized and not performed.
- Durable production authority issued: no.
- Production activated: no.
- Receiver/model invoked: no.
- Machine security/profile/ACL mutation: no.
- Push: no.

Next boundary: normalize this evidence and requalify the final exact five-file
staged tree. After a durable checkpoint, the next non-live design slice is the
watcher-owned retained-handle registry and native snapshot-provider contract.
Actual native API calls and all NQ-01 through NQ-12 process execution remain
separately governed.
