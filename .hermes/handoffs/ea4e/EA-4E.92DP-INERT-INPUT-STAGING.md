# EA-4E.92DP inert input staging

Status: NON-LIVE TEMP-FILE STAGING PASS / CONTAINER DELIVERY HOLD
Baseline: `70de3f9308982d373c73cb4fb49cc7cfade7d8bc`
Date: 2026-10-06 (America/Phoenix)

`tools/hermes_core/local_kilo_inert_inputs.py` writes the 92DO dummy
config and deny-all agent profile under a new root in the system temp
directory. It creates distinct `input` and `runtime` copies, verifies both
against the reviewed SHA-256 after writing, and returns only paths, hashes,
and `launch_authorized=False`. An existing root, a repository path, or a
corrupt write denies. No pre-existing user file is overwritten or deleted.

This is local fake-only staging, not a Docker mount, read-only ACL, or
independent immutability proof. The input copy is separate from the runtime
copy so a future Kilo rewrite can be detected without rewriting the
reviewed input. The local-Docker profile explicitly trusts administrators;
this file layout does not protect against them.

Verification: temp-only staging, plan, image-admission, fake-gateway,
request-shape, and Kilo adapter tests: 184 passed, one skip, zero failed.
Tests confirmed distinct copies, retained source hash after a runtime
rewrite, refusal to reuse an existing directory, repo-path denial, and
fail-closed detection of a simulated corrupt write. No container, Kilo
process, gateway listener, or model request occurred.

Next: freeze the precise read-only input and writable runtime mount
contract, including ownership, tmpfs limits, daemon observations, and
post-run rewrite accounting. A separately authorized fake-provider
container probe is required before claiming delivery works in Docker.

`TEMP_INPUT_STAGING=PASS_FAKE_ONLY`
`CONTAINER_CONFIG_DELIVERY_QUALIFIED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
