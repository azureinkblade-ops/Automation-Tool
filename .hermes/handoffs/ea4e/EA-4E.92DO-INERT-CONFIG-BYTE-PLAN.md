# EA-4E.92DO inert config byte plan

Status: NON-LIVE PURE CONFIG PLAN PASS / DELIVERY HOLD
Baseline: `060b5bbde989868a2a3b68fe72858ffd20e07427`
Date: 2026-10-06 (America/Phoenix)

The 92DN non-launchable Linux Kilo plan now generates canonical JSON text
and SHA-256 for exactly two future runtime files: a dummy-only
`kilo.jsonc` and a deny-all agent profile. This follows the existing 92CK
fake-provider config shape without importing its listener or launcher.
The endpoint remains `fake-gateway.invalid`; the API key is the public
dummy marker `EA4E_INERT_ONLY`, not an upstream credential. The plan is
deterministic and does not write either file.

`config_delivery=UNRESOLVED_NO_FILES_WRITTEN` prevents this plan from being
interpreted as a qualified mount or runtime handoff. Kilo's prior dummy
probe rewrote its config at runtime, so a future container contract must
keep reviewed input bytes separate from the writable runtime copy and
account for that rewrite. The unresolved network peer identity and dynamic
request-body gateway policy from 92DM also remain open.

Verification: 179 passed, one skip, zero failed across the pure plan,
image admission, fake gateway/request shape, and Windows Kilo adapter tests.
No container, Kilo process, gateway listener, or model request was made.

`INERT_CONFIG_BYTES_HASHED=YES`
`CONFIG_FILES_WRITTEN=NO`
`CONFIG_DELIVERY_QUALIFIED=NO`
`CONTAINER_LAUNCH_AUTHORIZED=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`MODEL_INVOKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
