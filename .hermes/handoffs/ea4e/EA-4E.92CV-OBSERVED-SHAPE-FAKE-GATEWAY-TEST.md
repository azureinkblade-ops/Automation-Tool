# EA-4E.92CV Observed-shape fake gateway boundary test

Status: NON-LIVE TEST PASS / PRODUCTION GATEWAY HOLD
Baseline: `ab607987eb5bec67768ed3a419948585c3bac6b1`

The 92CR dummy-only run observed a 64,878-byte streaming request with two
messages and seven recorded top-level field types. A synthetic body now
reproduces only that field-type and message-count shape. It uses repeated
placeholder content, not the captured prompt, request body, or credentials.

The existing fake gateway still requires the exact body SHA-256 in its
pre-authorized `KiloFakeScope`; this test does not relax that boundary. With
injected fake SSE only, it accepts the synthetic shape at 64,878 bytes and
at the current 65,536-byte edge, consumes one durable budget, and rejects a
second request. A well-formed 65,537-byte body with its own pre-authorized
hash is denied before the fake response callback or budget claim.

The directly affected fake gateway and sanitizer tests passed 31 with one
expected skip. The broader fake-only Kilo, streaming, and one-call control
set passed 89 with four expected skips. No listener, Kilo process, real
provider/model call, GPU, or ComfyUI operation occurred.

This is fixture compatibility for the one observed shape, not a production
request schema or a recommended 65,536-byte production cap. It does not
resolve dynamic request-body authorization, same-user peer identity, new
sealed custom-provider IDs, or the independent 92S mapped-byte requirement.
Production activation remains off.
