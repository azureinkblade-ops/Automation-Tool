# EA-4E.92EV Gateway Placement Decision Hold

Status: NON-LIVE DESIGN / IMPLEMENTATION CHOICE HOLD
Baseline: `0b469829ea8017b8a987908e62e44fada119b9e1`
Date: 2026-10-07 (America/Phoenix)

The accepted 92DE local-Docker profile and 92EO inert peer observation make
one private-network exchange plausible, but they do not establish a real Kilo
gateway topology. 92DW is networkless: its socket context, daemon reader,
and responder are injected. 92EQ-92EU narrow those seams under fake tests,
but no request reaches them from a real accepted socket.

## Placement choices

1. **Host listener:** the host could own the accepted socket, durable budget,
   and Docker daemon reads. However, a Linux container's route to a Windows
   host listener on the proposed internal network is unproven. Publishing a
   gateway port or using `host.docker.internal` would change the frozen 92DX
   no-published-port candidate and needs a separate reviewed contract.
2. **Gateway container:** the 92EO topology already demonstrated a held-open
   request between two inert containers. A trusted gateway image could parse
   the bounded body and hold it while a host authority checks a fresh daemon
   snapshot and durable one-send budget. But a signal alone is not a
   production release protocol: the request digest, attempt, nonce, response,
   and cancellation state would need an authenticated control channel with
   replay and crash accounting. Trusting in-container schema validation or
   moving the durable store into the container is an explicit authority
   relocation, not a consequence of the inert probe.

The container gateway is the narrower network fit **for design exploration**,
because it preserves the demonstrated internal two-container topology. It is
not selected for implementation or live use until its image identity,
control channel, body-validation owner, durable-claim owner, and teardown
rules are frozen and fake-tested. Neither option may inherit the existing
Windows Kilo adapter identity or the exact-hash fixture's approval.

Next bounded non-live design should specify one request lifecycle from
accepted socket through body validation, fresh peer observation, revocation,
one-send claim, response/release, and exact-ID cleanup, including crash and
replay cases. Only then should a fake gateway listener be implemented. A
separate exact one-shot authorization is required before a real Kilo
container, model, or production activation.

`GATEWAY_PLACEMENT_SELECTED=NO`
`HOST_INTERNAL_ROUTE_PROVED=NO`
`CONTAINER_CONTROL_CHANNEL_DEFINED=NO`
`BODY_VALIDATION_OWNER_FROZEN=NO`
`DURABLE_CLAIM_OWNER_FROZEN=NO`
`PRODUCTION_READY=NO`
