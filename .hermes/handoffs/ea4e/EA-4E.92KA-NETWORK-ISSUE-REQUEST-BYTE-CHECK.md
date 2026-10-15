# EA-4E.92KA network issue-request byte check

Status: NON-LIVE IMPLEMENTATION / NO AUTHORITY ISSUED.
Governing source: `b3ff31615377414cc45aecb51374bbb7c5174961`.

`tools/hermes_core/agent_local_docker_network_request_check.py` is a
standard-library-only, pure checker for the first 92JU Docker mutation
candidate, `network_create`. It requires the exact request schema and field
set, independently supplied request/source/Docker/attempt/operator/network
expectations, a deterministic fake-only network name, the four fixed
fake-profile labels, canonical request hash, reconstructed network-create
arguments, and all four authority flags set to false. An extra authority ID,
changed endpoint, changed labels, broader TTL, or mismatched argument vector
is denied. The existing 92JV builder's output is accepted as **data only**.

The checker does not establish that its expected values came from an
independent operator or protected policy. A caller can supply self-consistent
expectations; the fixed fake-profile rules still reject out-of-policy label
variants, but this function cannot issue, claim, or consume authority. It has
no store, Docker client, process launcher, network call, or UAC capability.
It is not yet installed in a protected closure and must not be executed as
an elevated worktree import. The 92JY source/ACL boundary and 92JU separate
issuer/store remain open.

Focused tests: 22 passed, 0 failed. The adjacent fake-only ladder must be
rerun against the final committed tree before this checkpoint is accepted.
No Docker mutation, receiver/model call, GPU, ComfyUI, or production
activation occurred. Production remains HOLD.
