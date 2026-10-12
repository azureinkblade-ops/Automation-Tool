# EA-4E.92HP Durable Text Process Intent

Status: NON-LIVE / NO PROCESS CAPABILITY. Parent: EA-4E.92HN.

The accepted Kilo/OpenCode attempt can now reserve one immutable process
intent before authorization consumption or receiver start. The row binds
delegation, receipt, launch, STARTED result, invocation bridge, task-input
hash, accepted idempotency/runtime IDs, and one command argv digest. It does
not persist task text or raw argv. Reservation rechecks active delegation,
lease, receipt, and bridge under the same SQLite write transaction; it denies
an existing receiver-start fence or terminal row. A second reservation,
including an identical one, is reconcile-only and denied. Historical read
verifies canonical payload and checksum without granting current authority.

Focused tests cover both receivers, restart read, altered command, cancelled
authority, an already-claimed fence, corrupt row, and two independent SQLite
writers contending for one attempt. The affected fake-only ladder passed
170 tests, 0 failed before commit.

This row is **not** a process-start permit. The later owner must revalidate
current authority, exact plan/command, authorization consumption, and the
one-shot fence before starting one receiver; cross-store checks are not an
atomic transaction. Concrete process/byte observation and capture remain
missing. No real receiver/model, network, Docker, GPU, ComfyUI, or production
activation was invoked. `PRODUCTION_READY=NO`.
