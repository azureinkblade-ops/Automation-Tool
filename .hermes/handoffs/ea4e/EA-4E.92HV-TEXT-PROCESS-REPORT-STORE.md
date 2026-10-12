# EA-4E.92HV Text Process Report Store

Status: NON-LIVE / REPORTED FACTS ONLY / PRODUCTION_READY=NO.

`SQLiteAgentTextProcessObservationStore` now retains one reported process
start and one bounded raw-byte terminal report per accepted Kilo/OpenCode
attempt. Start recording requires the reserved exact command, durable
authorization-claim lineage, receiver-start fence, and active task/lease.
Start duplicates deny. Terminal recording binds the same owner ID and PID,
hashes retained stdout/stderr bytes, permits identical replay, denies
divergent replay, and remains available for accounting after cancellation.
Historical reads verify checksums and bytes after restart.

Qualification: 7 focused tests; 190 affected tests passed, 0 failed.
Tests use fabricated process reports only. No process, receiver, model,
network, Docker, GPU, ComfyUI, or production activation was invoked.

The store does not attest that its caller owns a real process or that the
reported bytes came from a process. A fence plus claim-intent row is not
independent proof that external authorization consumption succeeded. The
next owner must supply controlled process handles, observed start and exit,
raw-stream retention, exact command/binary/transport binding, and fail-closed
reconciliation. No result may be returned from this report alone.
