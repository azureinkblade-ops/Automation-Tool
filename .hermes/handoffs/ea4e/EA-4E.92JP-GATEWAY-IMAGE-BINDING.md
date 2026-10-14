# EA-4E.92JP gateway image binding

Status: NON-LIVE REQUEST CONTRACT ROLL / NO ISSUER OR DOCKER MUTATION.
Governing predecessor: `62cda1ab87cab2b18a4b64e797f90d47aba69a17`.

The 92JO create issue-request schema advanced from v1 to v2. Its canonical
hash now includes the repository's pinned fake-gateway image reference,
index digest, and Linux/amd64 manifest digest. The request still binds
the proposed Kilo image separately. No caller can replace the gateway
image identity through the builder's arguments.

This closes only a missing request binding. It does not inspect a gateway,
prove its owner or image at runtime, create a network/container, issue an
authorization, consume a claim, or grant a start permit. The existing
`operator_verified`, `network_ownership_verified`,
`gateway_ownership_verified`, `issue_authorized`, `create_authorized`,
and `launch_authorized` fields remain false. The earlier v1 request is not
silently reinterpreted as v2; any future issuer must reject stale hashes.

The 92JO focused tests passed 11/11 and the adjacent fake-only ladder
passed 333/333 before commit. Next: bind independently verified durable
network/gateway ownership and current image observations, then freeze the
separate one-shot create issuer and claim store. Production remains HOLD.
