# EA-4E.92EW Source-Only Kilo Fake Gateway

Status: SOURCE-ONLY HELPER PASS / IMAGE AND RECEIVER HOLD
Baseline before this change: `40cdb2d7829db23f8077c401787229a75f3fac27`
Date: 2026-10-07 (America/Phoenix)

A separate Node helper now models a single fake Kilo provider request inside
the candidate two-container topology. It accepts only one
`POST /v1/chat/completions` with `application/json`, reads at most 65,536
bytes, hashes without logging raw body or authorization, emits only the
observed socket peer, body size, and SHA-256, then holds the response until
one explicit release. Release returns a fixed inert SSE body. Wrong route,
empty or oversized body, aborted client, report failure, and timeout deny;
the response cannot be released afterward. The 65,536-byte cap deliberately
matches the existing 92CP request-shape validator; 92CR's 64,878-byte
capture leaves little headroom and any future increase needs separate review.

The Dockerfile is source-only and pins the already-used base digest. No image
was built, no gateway server was started, and no Docker network/container,
Kilo receiver, model, provider, GPU, ComfyUI, or production activation ran.
Node unit tests: 10 passed, 0 failed, including the predecessor held-open
helper. The helper does **not** parse full Kilo JSON schema, verify a child
token, inspect Docker membership, or make a durable one-send claim. SIGUSR2
release is suitable only for a separately governed fake probe, not a
production control channel.

Next non-live work must freeze the fake-probe coordinator and exact image,
network, input-mount, peer, release, and cleanup checks. Any image build or
inert/real Kilo container probe needs its own bounded authorization. The
strict 92AT mapped-byte route remains REJECT; the accepted local profile's
provenance and production claims remain unearned.

`SOURCE_ONLY_FAKE_GATEWAY=PASS`
`IMAGE_BUILT=NO`
`GATEWAY_STARTED=NO`
`KILO_RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
