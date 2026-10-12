# EA-4E.92HT Text Command Revalidation

Status: NON-LIVE / FAKE-ONLY / PRODUCTION_READY=NO.

The durable Kilo/OpenCode process intent now exposes `verify_command`. It
rechecks the reserved argv hash, accepted receipt/launch/STARTED/task/runtime
lineage, current bridge hash, and active delegation/lease under a SQLite read
transaction. A different command or cancelled delegation is denied. The
method returns the existing intent, not permission to start a process.

Qualification: 12 focused tests and 178 affected tests passed, 0 failed.
Both receivers are covered. No receiver, model, Docker, GPU, ComfyUI, or
production activation was invoked. No terminal provenance is claimed.

Open boundary: a concrete trusted process owner must bind the verified
command to an observed process and durable terminal bytes, with exact
crash/replay behavior and separately authorized live qualification. A
read-time check alone is not atomic with a later process start and must not
be treated as a start permit.
