# EA-4E.92DN Linux Kilo inert plan

Status: NON-LIVE PURE PLAN PASS / RECEIVER LAUNCH HOLD
Baseline: `b46847db7cb506583628e75c2c33f18dba896359`
Date: 2026-10-06 (America/Phoenix)

`tools/hermes_core/local_kilo_inert_plan.py` returns a fixed, deterministic
description of a future dummy-only Linux/amd64 Kilo probe. It binds the
92DJ/92DK platform manifest and local index identities, non-root user,
read-only rootfs intent, Linux home/config/work paths, fixed Kilo argv,
deny-all agent policy, a dummy key, and an `.invalid` fake-gateway URL.
The returned plan has `launch_authorized=False` and an unresolved network
binding. It does not write config files, create a network/container, start
Kilo, contact a provider, or grant authority to do so.

This separate plan leaves the Windows Kilo adapter, its sealed transport ID,
and the existing exact-hash fake gateway unchanged. It cannot resolve the
task-dependent request-body authorization gap identified in 92DM. The
gateway address is intentionally non-routable; a later fake-provider
container probe needs a reviewed network/peer-identity contract and its own
bounded authorization before that value changes.

Verification: new pure-plan tests plus image admission, existing fake
gateway/request-shape, and Kilo adapter regressions: 178 passed, one
existing skip, zero failed. No container or receiver operation occurred.

Next non-live work: specify immutable runtime config bytes separately from
mutable home/cache, then fake-test created-container effective settings and
gateway peer attribution. Do not treat this data plan as a launcher.

`LINUX_KILO_INERT_PLAN=PASS_FAKE_ONLY`
`CONTAINER_LAUNCH_AUTHORIZED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`PRODUCTION_GATEWAY_QUALIFIED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
