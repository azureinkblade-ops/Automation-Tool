# EA-4E.92CM Kilo inert host-probe result

Status: ONE-SHOT INERT HOST PROBE COMPLETE / PRODUCTION READINESS HOLD
Source commit: `ffe77c13cb332350f2d36f8a3d686c6acc0c1a05`
Pinned Kilo 7.8.3 executable SHA-256: `8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a`

The operator explicitly authorized one dummy-provider probe on this host while
accepting that absence of unrelated outbound traffic could not be proved. No
production activation, real provider credential, GPU, or ComfyUI use was
authorized. The prepared plan's `network_isolation_verified` and
`real_provider_calls_authorized` flags remained false.

The initial direct-file launcher invocation failed at Python import before
creating the one-shot claim or starting Kilo. The same committed launcher was
then invoked as a Python module. It created the durable one-shot claim and
started exactly one observed Kilo process (PID 12084), which exited 0 after
5.106 seconds; no Kilo process remained at postflight. There was no automatic
retry and the claim prevents another run in the prepared home.

The local fake provider recorded exactly one request: `POST
/v1/chat/completions`, HTTP 200, `stream: true`. It did not forward traffic.
The bounded CLI output contained the exact `EA4E_INERT_OK` text event. The
output did not overflow and no capture error or timeout occurred. The
sanitized machine-readable result and claim are in the prepared runtime
directory as `probe-result.json` and `attempt.json`; raw output, prompt body,
and authorization headers were not retained.

This qualifies the observed custom OpenAI-compatible *inert* request shape,
including streaming, for the gateway design. It does not qualify the current
production Kilo provider/model route, prove no other host egress, prove no
real model invocation outside the observed fake endpoint, implement a durable
one-upstream-request gateway, or close the independent EA-4E.92S exact
mapped-byte HOLD. Production activation and a live provider pilot remain HOLD.

Next non-live slice: bind the observed streaming request schema to a reviewed
custom-provider gateway contract, then fake-test durable one-request claim,
concurrency/replay, cancellation, timeout, and stream truncation. Any real
upstream use requires its own exact authorization after those gates.
