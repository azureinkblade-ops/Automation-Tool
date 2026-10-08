# EA-4E.92FK Pinned Inert Running Driver

Status: NON-LIVE FAKE-CLI QUALIFIED / DOCKER RUN HOLD
Baseline: `5ba5d3f32b5262543a4be0fc2d2dfb1ecd43d78d`
Date: 2026-10-08 (America/Phoenix)

The pinned fake-gateway Docker driver now supports the 92FJ inert running
sequence without a release or signal method. It checks each start against the
exact created ID, run name, image reference, label, and prestart state. A
gateway log read is scoped to that ID and a 10-second coordinator deadline;
the reader accepts only one strictly parsed pending-event line and rejects
stderr. Cleanup verifies the exact name/label/image and expected ID before
removing a running object; when a create result was lost, it will remove only
an unstarted matching object. Network removal follows container removal and
run-label listings must show zero leftovers.

All new tests use an injected fake Docker CLI and an inert fake executable.
The affected ladder passed **119/119**, including lost start/create responses,
foreign-label denial, malformed/multiple log lines, stderr denial, unowned
start refusal, and exact cleanup. No real Docker command, container start,
network request, Kilo/OpenCode receiver, model, GPU, ComfyUI, or production
activation occurred in 92FK.

This is a runtime-capable implementation but not a runtime qualification.
Before one separately authorized inert run: reverify the source commit,
installed CLI hash, pinned images, empty run-scoped names, test gate, and
the exact one-shot object/signal budget. The coordinator does not signal
release; the client request will remain pending until forced owned cleanup.
An observed event and two fresh running matches would still be candidate
evidence, not authenticated control or production readiness.

`FAKE_CLI_TESTS=119_PASSED_0_FAILED`
`REAL_DOCKER_COMMANDS=0`
`RELEASE_SIGNAL_CAPABILITY=NO`
`RECEIVER_EXECUTED=NO`
`PRODUCTION_READY=NO`
