# EA-4E.92DX Docker peer-binding contract review

Status: NON-LIVE DESIGN / PEER VERIFICATION HOLD
Baseline: `a6a014af74e0d685f61884529a8982b117eb299c`
Date: 2026-10-06 (America/Phoenix)

92DW's injected peer callback is a test seam, not a Docker peer verifier. This
review defines the next bounded qualification under the separately accepted
92DE local-container profile. The Windows host administrators, Docker daemon,
and Docker-control account are trusted only in that alternative profile. It
does not alter the strict 92AT/92CZ mapped-byte REJECT/HOLD.

Docker documents that a user-defined bridge permits container-to-container
communication, while `--internal` restricts external network access but still
allows host communication with a container IP. Therefore an internal bridge,
unpublished gateway port, DNS name, or child token is insufficient alone to
identify a requesting container. No network was created for this review.

## Candidate admission boundary

1. Create a fresh, per-attempt, daemon-reported internal bridge with a unique
   network ID. Deny any reused network, published port, host network, extra
   receiver network attachment, or unexpected member. Pin the exact receiver
   and fake-gateway container IDs and image/config identities before start.
2. The gateway must use the accepted socket's observed remote address, not an
   HTTP header, forwarded address, DNS name, or caller-supplied container ID.
   Compare it to the receiver endpoint address from a fresh trusted-daemon
   inspection of the exact network ID and container ID. Require one unique
   matching endpoint and only the two expected network members.
3. Reinspect membership and container state immediately before the durable
   92DW one-send claim. Deny missing, changed, ambiguous, stopped, or
   multi-homed receiver state; a bearer token never resolves a mismatch.
   No automatic retry or claim refund follows an uncertain send.
4. The receiver gets only a child-only credential and no upstream credential.
   The fake gateway has no provider route. Cap request/response bytes and time,
   prohibit redirects, and record sanitized membership, socket address,
   decision, claim, and teardown evidence without raw prompts or tokens.
5. One owner must reconcile container, gateway, and network identities after
   normal exit, cancellation, or crash. Reuse of an old network/container ID
   or one-send budget is denied. Cleanup is limited to exact owned objects.

This is a **candidate under the local trust model**, not independent process
attestation. Before treating it as qualified, fake-test wrong socket address,
spoofed forwarded headers, changed endpoint, extra member, extra attachment,
stale daemon observation, host-origin request, restart/replay, concurrent
requests, and teardown failure. Then inspect Docker Desktop's actual observed
socket/daemon behavior in a separately authorized inert probe. The present
documents do not establish that behavior, so the real peer verifier remains
unqualified. No receiver, network, credential, or model call is authorized.

Docker primary references:
- https://docs.docker.com/engine/network/drivers/bridge/
- https://docs.docker.com/reference/cli/docker/network/create/
- https://docs.docker.com/reference/cli/docker/network/connect/

`DOCKER_PEER_BINDING_CONTRACT=DRAFT_NONLIVE`
`DOCKER_PEER_VERIFIER_QUALIFIED=NO`
`LINUX_KILO_RECEIVER_EXECUTED=NO`
`REAL_UPSTREAM_SEND_AUTHORIZED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
