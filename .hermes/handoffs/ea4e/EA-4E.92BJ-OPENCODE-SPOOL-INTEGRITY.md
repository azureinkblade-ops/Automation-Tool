# EA-4E.92BJ OpenCode Spool Integrity

## Boundary

Non-live correction from synchronized parent
`b5c1557e262ecd56673d3e7967d85d739d320f4b`. No receiver, model,
provider/network, GPU, ComfyUI, production activation, or native parser
worker was invoked. This checkpoint does not authorize a live call.

## Correction

The OpenCode stream readers previously wrote bounded spool files, while
`poll()` accepted whatever bytes were present at read time. A same-size
replacement after a reader finished could therefore be parsed as the process
output. The readers now hash retained bytes while writing and flush/fsync
before completion. `poll()` checks each file's exact length and SHA-256 before
returning a result. It fails closed on mismatch and marks the process result
collected only after both reads verify. Process-free tests cover same-size
replacement and truncation after reader completion.

This is an in-process consistency check, not authenticated evidence against
an actor able to modify process memory. It does not make spool paths immutable,
fsync the parent directory, create a durable lineage manifest, bind a raw
capture to a task/authorization/model identity, or establish independent
offline replay. Streams above the retention cap remain truncated and cannot
be verified as successful receiver results.

## Verification

Pinned stage2-v2 Python with fake-only process, filesystem, and non-live
report-host guards:

- Process-free OpenCode adapter: 75 passed, 16 helper-process cases
  deselected; zero guard events.
- OpenCode downstream ladder: 320 passed, 17 deselected, zero guard events.
  One deselection is the historical EA4 OpenCode replay capture absent from
  this machine; it remains an open evidence gap, not a passing test.
- Complete guarded Hermes Core: 4,544 passed, 35 raw inherited failures,
  six established OS-process tests deselected, 104 subtests passed. All 35
  failure identities exactly match the EA92BI baseline. Process guard denied
  32 helper launches; filesystem guard events were zero. Raw suite is not
  green. JUnit `.pytest-ea4e92bj-full-a/result.xml`, SHA-256
  `a594fed51991861d7a90543bf3cc78697ba5ba329f46dea99360796688f876d0`.

The first adapter run intentionally exposed 15 helper-process cases to the
fake-only guard; they failed at the guard, not in the changed logic. They were
excluded in the recorded process-free run.

## Remaining Hold

No capture-only live entry point, independent raw replay manifest, CPU-only
model proof, provider egress containment, or exact live authority is supplied
here. EA92S exact mapped-byte invariant remains REJECT/HOLD.
