# EA-4E.92CN Kilo fake gateway qualification

Status: NON-LIVE FAKE-ONLY PASS / PRODUCTION GATEWAY HOLD
Baseline: `42e7564b1bbf8a163aa029f8820ad8ec7b186e30`
Inputs: `EA-4E.92CJ-KILO-ONE-REQUEST-GATEWAY-DESIGN.md` and
`EA-4E.92CM-KILO-INERT-HOST-PROBE-RESULT.md`

The 92CM one-shot inert Kilo probe observed one `POST /v1/chat/completions`
with `stream: true`, HTTP 200 and the expected output marker. It did not
retain the request body or headers. The exact generated request schema and
any unrelated host egress therefore remain unproved.

This checkpoint adds `tools/ea4e92cn_kilo_fake_gateway.py` as an
acceptance-only, networkless fixture. It uses the existing durable
invocation-authorization store with a distinct `kilo-cli-agent` receiver
identity, a fixed fixture request hash, a local fake-token hash, a bounded
streaming chat-completion route, and the existing bounded SSE inspector.
The durable claim occurs before the injected response callback. Duplicate
or concurrent requests, post-restart replay, out-of-scope calls, expiry,
cancellation, and revocation are denied. A fake callback timeout or invalid
stream consumes the budget; there is no refund or retry. A precommit store
failure never calls the callback. The module has no socket listener,
subprocess launch, real credential, or upstream HTTP client.

Combined affected gate: 192 passed, 2 skipped across the Kilo fixture,
existing streaming/claim suites, inert probe, and Kilo adapter tests. The
two skips are the consumed one-shot prepared-plan test and a prior opt-in
test; neither is a failed assertion.

The raw full `tests/hermes_core/` run was not green: 4,744 passed, 20 failed,
3 skipped, 104 subtests passed. Representative failures reproduced alone.
They involve a missing historical Codex executable pin, frozen Python
interpreter/source mismatches in older process guards, an absent Kilo 7.7.9
candidate, and a missing historical OpenCode JSONL capture. The 92CN
module is imported only by its new tests, which all passed; no existing
production module or test imports it. These 20 remain visible as separate
environment/historical-contract failures, not normalized to passing.

This is not the production gateway. Fixture issuance is not a production
authorization; its fixed body hash is not a captured Kilo production request.
No transport/model binding, credential reference, sealed ID, app route, or
production activation changed. The next non-live work is to review the
Kilo-generated request fields and local-token handoff without rerunning the
consumed 92CM probe, then design and qualify a production-capable gateway
with an independently bound upstream credential and durable request budget.
That design still needs redirect/retry prohibition, bounded streaming,
teardown, and affected contract resealing. The separate 92S exact
mapped-byte HOLD remains, and no real provider/model execution is authorized.
