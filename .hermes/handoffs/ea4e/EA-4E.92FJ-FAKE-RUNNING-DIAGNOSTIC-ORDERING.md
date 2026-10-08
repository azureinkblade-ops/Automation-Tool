# EA-4E.92FJ Fake Running Diagnostic Ordering

Status: NON-LIVE FAKE-DRIVER QUALIFIED / REAL PROBE HOLD
Baseline: `677c02a6bcdff864fec18d130b9e502dfa74d8f9`
Date: 2026-10-08 (America/Phoenix)

The new injected-driver coordinator preserves the successful 92FI preflight
and exact created-state gate before either fake start. It then observes one
strict pending-event line and requires two separately acquired running
network/container snapshots to match the event body and client socket-peer
candidate. It has no release/signal method and always calls its injected
owned-object cleanup on success or failure, requiring zero run-scoped
leftovers. Every result remains `peer_qualified=False` and
`production_ready=False`.

The coordinator has no concrete Docker driver or CLI entry point. Its only
new tests use an in-memory fake driver; they cover operation order, two fresh
reads, invalid event, start failure, created/preflight denials, running-record
denial, second-snapshot identity drift, and unconfirmed cleanup. The complete
affected fake-only ladder passed **110/110**. No Docker object was created or
started for 92FJ. No request, signal, Kilo/OpenCode receiver, model, GPU,
ComfyUI, or production action occurred.

Next: qualify a bounded concrete inert running-probe driver with pinned CLI,
exact owned-ID cleanup even after lost command results, strict stdout source
and length checks, and no automatic retry. A separately approved one-shot
Docker run would still be required to observe a real pending socket peer.
Neither the 92FI created-state result nor fake-only 92FJ tests authorize it.

Post-checkpoint correction: the coordinator now supplies a 10-second maximum
to the injected pending-event reader. Its fake-driver test asserts that exact
argument. The same affected ladder passed 110/110 after this correction;
there was still no concrete driver or Docker run.

`FAKE_ONLY_TESTS=110_PASSED_0_FAILED`
`CONCRETE_RUNNING_DRIVER=NO`
`DOCKER_OBJECTS_CREATED=0`
`REQUESTS_SENT=0`
`RELEASE_SIGNALS_SENT=0`
`RECEIVER_EXECUTED=NO`
`PRODUCTION_READY=NO`
