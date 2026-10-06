# EA-4E.92DV synthetic dynamic-body shape candidate

Status: FAKE-ONLY SHAPE CHECK / FORWARD AUTHORITY OFF
Baseline: `f8e0631710c7eaf504797411ed6c96e9690356fc`
Date: 2026-10-06 (America/Phoenix)

Added a pure, separately named inert Kilo request-shape checker. It uses
the existing privacy-bounded parser to match the observed 92CR dummy
top-level field types, two message roles/content kinds, no unknown fields,
the dummy wire model, and streaming mode. It retains the parser's current
65,536-byte limit and returns only a byte count, SHA-256 digest, and an
explicit `forward_authorized: false`. It cannot listen, claim a budget,
start Kilo, invoke a provider, or send a request. The existing exact-hash
`KiloFakeGateway` was not modified.

Synthetic tests include the observed 64,878-byte size, changed model,
route-relevant field types, unknown fields, duplicate JSON keys, missing
messages, changed content kind, and oversize body. A negative proof uses
two different dummy prompt bodies that both match this shape but have
different SHA-256 digests. Therefore even a shape match cannot bind the
request to a delegation or authorize forwarding. This checker also does
not validate nested tool schemas or provide peer/container identity.

The focused new and predecessor suites passed 43 tests with 1 explicitly
gated loopback fake-provider test skipped. The combined fake-only Kilo
request/gateway/image/mount ladder passed 115 with 1 skip, 0 failures.
No Docker, Kilo,
gateway listener, credential, model, GPU, or ComfyUI action occurred.

The next qualification must add independent attempt/peer binding and a
durable one-send claim around any dynamic body; it must not treat a bearer
token or first observed body as sufficient. A Linux Kilo-to-fake-gateway
container run remains separately authorized and was not performed here.

`DYNAMIC_BODY_SHAPE_CANDIDATE=FAKE_ONLY`
`FORWARD_AUTHORITY=NO`
`LINUX_KILO_RECEIVER_EXECUTED=NO`
`PRODUCTION_GATEWAY_QUALIFIED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
