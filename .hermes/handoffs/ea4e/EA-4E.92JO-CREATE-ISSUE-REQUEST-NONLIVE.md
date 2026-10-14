# EA-4E.92JO create-only issue request

Status: NON-LIVE REQUEST SHAPE / NO ISSUER / NO DOCKER MUTATION.
Governing predecessor: `f4b6caab9c3cd40badc1d131345c350915d14b40`.

The pure builder re-verifies the reserved Kilo intent, prepared inputs,
92JC provisional spec, and 92JM create-request hash. It binds those hashes
to a reported source commit, Docker executable hash, exact Linux-engine
endpoint, image, deterministic container/network names, reported network
and gateway IDs, operator ID, nonce, and a TTL request no longer than five
minutes. It returns a deterministic request hash.

Every authority flag remains false: operator verification, network and
gateway ownership, issuance, create, and launch. IDs supplied to this
builder are untrusted reports, not independently verified facts. The
artifact contains no authorization ID, Docker argv, CLI invocation, or
receiver call. It does not create a durable claim or spend a mutation
budget. The production activation authorization is a different contract
and cannot silently serve as a Docker create permit.

Dedicated fake-only tests: 11 passed, 0 failed. Adjacent 92I/92J and
authority tests: 333 passed, 0 failed before commit. No Docker object,
Kilo/OpenCode receiver, model, GPU, or production activation was used.

Next: independently verify operator and network/gateway ownership, freeze
the exact issuer and durable authorization/store semantics, then implement
the 92JN claim. The process-tree-contained mutation driver and a separate
one-shot real create-only authorization remain additional gates.
Production remains HOLD.
