# EA-4E.92CO Kilo gateway contract-impact review

Status: NON-LIVE REVIEW / PRODUCTION BINDING HOLD
Baseline: `0596b6ff6d90e7fd86821bfda6430cf830fc11b5`

## Observed versus sealed routes

The one-shot inert probe used pinned Kilo 7.8.3 (executable SHA-256
`8b042a53c3d3e5e2043f37392c3d62e7d5c278dc7740d93aeb6fa91df7ccc63a`),
an isolated dummy config, and model `openai-compatible/ea4e-inert`. It
observed one streaming `POST /v1/chat/completions` to loopback. The 92CN
fixture proves a fake-only durable claim before one injected response, not
an upstream network boundary.

The current sealed production Kilo route in `kilo_adapter.py` fixes argv to
`kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`. Its transport
contract hashes the fixed argv, model value, environment, agent profile, and
process policy. `kilo_successor_binding.py` binds that transport and
`KILO_MODEL_BINDING_ID` into the successor identity;
`receiver_router.py` and `production_executor_binding.py` consume those
IDs. `kilo_live_binding.py` limits adapter calls, not HTTP requests made
inside the receiver. The custom-provider probe cannot be silently mapped
onto these sealed production identities or assumed to preserve free-tier
provider access.

## Required before any production gateway roll

1. Freeze a new, separately named custom-provider transport/model binding,
   including exact Kilo executable hash, argv, config source, agent profile,
   loopback endpoint, model mapping, and local token source. Do not overwrite
   the existing free-model binding in place.
2. Establish the request-body contract. The consumed 92CM probe recorded
   path, method, status, stream flag, and output marker, but deliberately did
   not retain body or headers. The 92CN fixture's exact body hash is test
   data, not a production Kilo request hash. Static inference alone cannot
   close this observation gap. A new receiver probe would need separate
   exact authorization and a privacy-reviewed, bounded schema capture.
3. Define a real upstream credential owner outside Kilo and the repository.
   The child may receive only an attempt-bound local token. The gateway must
   bind authorization, cancellation/revocation, expiry, source commit,
   executable/transport/model IDs, and one durable upstream-send claim.
4. Qualify actual gateway code with fake transports: no redirects, retries,
   fallback, or second send; concurrency and restart replay denial; crash
   between claim and send; bounded SSE output and timeout; cancellation,
   truncation, upstream error, and teardown. Do not equate 92CN's injected
   callback with a production-capable network gateway.
5. Roll all dependent sealed IDs and acceptance evidence against the new
   route, with the old route untouched, before requesting a separately
   governed one-request live pilot. The independent EA-4E.92S exact
   mapped-byte proof remains REJECT/HOLD regardless of gateway progress.

No production code, credential, launch setting, or live authority was
changed in this review. The next actionable non-live work is a design for
the privacy-bounded request-schema capture and local-token handoff. The
consumed 92CM one-shot authorization cannot be reused.
