# EA-4E.92DU Linux Kilo gateway contract hold

Status: NON-LIVE CONTRACT REVIEW / RECEIVER LAUNCH HOLD
Baseline: `d18b64b1bcce62c65fdd01ff41fa44a556c399f7`
Date: 2026-10-06 (America/Phoenix)

92DT qualified one inert dummy-file mount and non-root runtime write. It did
not run Kilo or create a network peer. The approval used for that probe is
consumed. A Kilo receiver container cannot inherit 92DT's authority.

The current `KiloFakeGateway` is deliberately a networkless fixture. It
requires a preauthorized `request_hash`, a 65,536-byte body cap, and an
injected fake response. The 92CR sanitized Kilo request was 64,878 bytes,
leaving only 658 bytes of cap headroom. Its body varies with the task, so
neither that recorded hash nor a new body observed from a bearer-token
holder may be treated as prior authorization. The existing fixture must
remain unchanged.

## Separate Linux-container contract to qualify

1. Name a new Linux Kilo receiver/transport identity and pin the image,
   config/profile input hashes, container identity, delegation, attempt,
   invocation authorization, gateway budget, and TTL. Do not alias the
   Windows Kilo adapter or its free-model route.
2. Use one per-attempt private, non-published network and a fake-only
   gateway peer. Verify the exact allowed container/network membership
   before a send. A bearer token alone, a first-request-wins rule, or
   `host.docker.internal` alone is insufficient peer attribution. Docker
   administrators remain trusted only under the separate local profile.
3. Carry a child-only one-shot credential. Keep any upstream credential
   outside the container and fake-only qualification. A source-side holder
   of the child credential must not gain a reusable gateway budget.
4. Validate method, path, content type, expected model, stream mode,
   message structure, tool fields, nested limits, duplicate keys, and
   finite numbers before durable claim. Choose a new body cap only after
   a bounded sanitized capture demonstrates headroom; do not silently
   raise the existing fixture's 65,536-byte cap.
5. After independently validating peer, authority, and body schema, claim
   the one-send budget durably before any fake response or later upstream
   send. Record only the observed body digest and bounded shape; do not
   retain prompt text, raw body, credential, or authorization header.
   Timeout, ambiguous send, or failed response never refunds the claim.
6. Verify cancellation/revocation before claim, and specify network,
   gateway, and container teardown/reconciliation after exit or crash.
   A successful fake response is not a real upstream qualification.

## Required next evidence

First qualify a pure dynamic-body validator and one-send fake gateway with
synthetic requests, including wrong peer, wrong task, replay, concurrent
claims, oversized/nested body, duplicate keys, cancellation, timeout, and
crash cases. Then request a distinct bounded authorization for a Kilo
container connected only to that fake gateway and capture a privacy-bounded
request shape. Only after that evidence may a real upstream pilot be
proposed. No Kilo container, model, network, or credential was used in
this review.

Existing fake gateway plus request-shape tests: 31 passed, 1 skipped,
0 failed. The skip is the explicitly gated loopback fake-provider test.

`INERT_MOUNT_DELIVERY=PASS`
`LINUX_KILO_RECEIVER_LAUNCH_AUTHORIZED=NO`
`DYNAMIC_BODY_GATEWAY_QUALIFIED=NO`
`REAL_UPSTREAM_SEND_AUTHORIZED=NO`
`PRODUCTION_ACTIVATED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
