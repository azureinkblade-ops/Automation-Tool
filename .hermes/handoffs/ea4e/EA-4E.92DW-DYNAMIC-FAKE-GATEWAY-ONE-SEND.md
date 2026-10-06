# EA-4E.92DW dynamic fake gateway one-send qualification

Status: FAKE-ONLY QUALIFIED / REAL PEER AND RECEIVER HOLD
Baseline: `e32f8e50ec78e7a6f763bdde2d0de321c7209e32`
Date: 2026-10-06 (America/Phoenix)

Added `ea4e92dw_kilo_dynamic_fake_gateway.py` as a separate networkless
acceptance fixture. The existing exact-body-hash `KiloFakeGateway` and its
65,536-byte cap were not changed. The new fixture has no listener or
upstream transport; it requires injected fake peer verification and fake
response callbacks. It binds a synthetic run, source commit, transport,
model binding, task hash, network/container identities, child-token digest,
and time window into a durable qualification-only invocation budget.

For each synthetic request, it checks the run/task, method, route, content
type, child token, injected peer decision, the 92DV inert body shape, and
cancellation/revocation/time before making one durable claim. The fake
response callback runs only after that claim commits. It returns only
response bytes plus observed request size/SHA-256; it does not preauthorize
an unknown body hash. A failed fake response or timeout does not restore
the one-send budget. The raw request body is not persisted by this fixture.

Focused tests cover wrong peer with a valid token, wrong task/route/token,
shape denial, expiry, cancellation/revocation, restart replay, concurrent
requests, precommit failure, timeout, bad fake response, and absence of
prompt content in the durable budget file. The focused new/predecessor
suite passed 53 tests. The combined fake-only gateway/request/image/mount
ladder passed 134 with 1 explicitly gated loopback test skipped and zero
failures.

**No production peer attribution is qualified.** The injected peer callback
is a fake seam, not evidence that Docker mapped an incoming request to the
pinned container/network. The body checker matches only the observed inert
shape and does not validate nested tool semantics. The callback receives
synthetic raw bytes in process; this fixture is not a production privacy
or upstream transport implementation. No container, Kilo process,
credential, provider, model, GPU, or ComfyUI call occurred.

Before any Linux Kilo-to-fake-gateway container probe, separately qualify
the private per-attempt network and independently observed peer identity,
freeze a bounded fake listener and cleanup owner, and obtain a new exact
one-shot receiver authorization. The 92DT inert mount approval is consumed.

`DYNAMIC_FAKE_ONE_SEND=PASS`
`PRODUCTION_PEER_VERIFIER=UNQUALIFIED`
`LINUX_KILO_RECEIVER_EXECUTED=NO`
`REAL_UPSTREAM_SEND_AUTHORIZED=NO`
`PRODUCTION_ACTIVATED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
