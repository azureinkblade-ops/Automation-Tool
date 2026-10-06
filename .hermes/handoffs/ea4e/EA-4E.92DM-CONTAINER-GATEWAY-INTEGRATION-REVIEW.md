# EA-4E.92DM container-to-gateway integration review

Status: NON-LIVE IMPACT REVIEW / RECEIVER AND UPSTREAM HOLD
Baseline: `461c5d142a7bdf2ec805000ec0099cac7cbbd1d0`
Date: 2026-10-06 (America/Phoenix)

## Controlling boundary

The operator accepted a separate local-Docker assurance profile in 92DE.
Local administrators and Docker control are trusted under that profile; the
strict 92AT/92CZ profile remains REJECT/HOLD. The 92DK `/bin/true` smoke and
92DL pure index/manifest binding do not qualify a Kilo receiver process,
network route, or model request.

The existing Windows Kilo adapter is not a Linux-container adapter. It pins
a Windows executable, Windows environment paths, a host-side agent profile,
and a free-model argv. The host-side profile also says
`live_authorized: false`. None of those source identities or authority IDs
may be reused for a Linux container by changing only the executable path.

## Existing gateway evidence

92CM and 92CR observed a Kilo 7.8.3 dummy-provider request to a local fake
endpoint: one streaming `POST /v1/chat/completions`; the 92CR sanitized body
was 64,878 bytes and included `stream_options`, `tools`, `tool_choice`, and
`max_tokens`. Kilo rewrote its isolated dummy config during the run. The
tests did not retain raw prompt, body, or authorization headers.

`tools/ea4e92cn_kilo_fake_gateway.py` is networkless acceptance code. It
requires a preauthorized exact body hash and a fixed 65,536-byte cap, then
claims one durable send before invoking an injected fake response. That is
correct for the synthetic fixture but cannot authorize a new task's
unpredictable Kilo-generated body. Neither the 92CR body hash nor its size
bound can be generalized to a production delegation.

## Contract to freeze before a Linux receiver adapter

1. Define a new Linux-container receiver/transport identity and sealed
   custom-provider/model route. Do not alias the Windows free-model route.
2. Define immutable per-attempt input config separately from writable Kilo
   home/cache/output. Pin the deny-all agent profile and validate any
   post-run config rewrite instead of silently trusting mutable output.
3. Bind one container and one isolated child credential to one delegation,
   execution attempt, invocation authorization, gateway budget, and TTL.
   The upstream credential stays gateway-only, never in the container.
4. Select and fake-test the gateway's request-identity rule for a dynamic
   body. A first request from any holder of a bearer token is insufficient
   without an independently checked container/attempt boundary. The local
   Docker profile may allow a private per-attempt network, but isolation and
   peer attribution have not been demonstrated.
5. Freeze allowed route, method, content type, request fields and nested
   limits, duplicate-key handling, explicit body size with measured
   headroom, stream framing, response cap, timeout, redirect policy, and
   no-retry behavior. Denial or uncertain send never refunds the one-send
   budget.
6. Specify daemon pre-start and post-start observations, container/network
   cleanup owner, cancellation, crash reconciliation, and durable evidence
   without storing raw prompts or credentials.

These are not instructions to issue a real credential, attach a network,
start Kilo, or call a model. The first implementation slice should use pure
plans and fake request/response tests; existing fixture hash checks must not
be weakened in place. A separately bounded Kilo fake-provider container
probe, then a real upstream pilot, require distinct authorizations.

Current fake gateway, request-shape, and image-admission tests: 59 passed,
one skipped, zero failed. This is targeted non-live evidence, not a full
production regression or an executed Linux receiver.

`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`LINUX_KILO_TRANSPORT_QUALIFIED=NO`
`PRODUCTION_GATEWAY_QUALIFIED=NO`
`ONE_REAL_UPSTREAM_SEND_AUTHORIZED=NO`
`RECEIVER_EXECUTED_THIS_CHECKPOINT=NO`
`MODEL_INVOKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
