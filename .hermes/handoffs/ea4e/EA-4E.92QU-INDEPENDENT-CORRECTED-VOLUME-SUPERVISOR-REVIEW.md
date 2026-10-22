# EA-4E.92QU Independent Corrected Volume Supervisor Review

One separately approved independent, read-only reviewer matched all five
requested `<commit>:<path>` Git blob SHA-1 values at
`6ebdb7d2e7bd640e88fe9dc24047cab53ea90444` before substantive review.
Attributable report: Codex thread `01a163e1-ae34-70b2-831d-eda914b1e7d9`.
The one-review approval is consumed.

Source-only decision: **HOLD**. The ordinary 92QS late-result and failed-kill
paths were corrected, but the reviewer found:

1. Medium: executable hashing, process spawn, and stream closure are not
   elapsed-time bounded. Exceptional cleanup can add time past the deadline.
   UTC wall-clock checks are not a monotonic elapsed-time guard. A late
   positive result is rejected when observed, but this is not a hard
   end-to-end execution bound.
2. Low: a reader is registered only after `start()` returns. If startup
   launches and then raises, cleanup cannot join or observe that reader and
   may close its pipe while it remains active.

The reviewer observed that recalculated remaining time before process wait
and joins, final expiry denial, independent wait after kill failure, and
denial on tracked reader/close uncertainty are present. The reviewer read
the fake tests but did not execute them. The tests do not establish blocking
closure, launch-then-raise startup, clock rollback, or native containment.

Known open boundaries also include mutable-path hash/spawn provenance,
mutable dependencies, process-local one-use, unauthenticated ceremony,
protected installation, and durable ledger. Native qualification HOLD;
receiver/model HOLD; trusted issuer and production HOLD; strict 92AT
mapped-byte proof REJECT. No files were changed by the reviewer and no
test, executable, native probe, Docker, receiver/model, GPU, ComfyUI, or
production action occurred.

Next non-live decision: handle the reader-start tracking edge in source,
but do not claim that another synchronous Python timeout check can provide
the required hard end-to-end bound. That bound needs a separate reviewed
containment mechanism or a revised, explicitly weaker contract.
