# EA-4E.92HG Delegated Issue-Request Preflight

Status: NON-LIVE / FAKE-ONLY. Parent: EA-4E.92HF.

`preflight_agent_issue_request` requires an existing 92HF reservation, then
replays `reserve` to recheck active delegation, lease, start, terminal, and
executor-binding state. It compares the explicit issuer request's execution
request ID, receiver, binding ID, and enablement ID with the reserved bridge.
A missing reservation is denied without creating one. Swapped values,
cancellation, and a prior receiver-start claim deny. This check does not call
the issuer or authorization store, does not launch a process, and grants no
execution authority.

The preflight and a future issuer call are not atomic across the delegation
and invocation-authorization stores. A successful preflight is not a usable
start gate: cancellation/revocation, authorization claim, and receiver-start
fence must be rechecked by the trusted owner at their respective durable
boundaries. A crash after an irreversible claim must yield UNKNOWN, not retry.

Focused preflight plus predecessor ladder: 61 passed, 0 failed. The staged
ladder including the unchanged issuer and app provisioner: 141 passed,
0 failed. No real
receiver/model, network, Docker, GPU, ComfyUI, or production activation.
`PRODUCTION_READY=NO`.

Next: design and qualify the durable authorization-to-reservation claim link
without treating this preflight as sufficient authority. The trusted process
owner and terminal-byte proof remain separate prerequisites.
