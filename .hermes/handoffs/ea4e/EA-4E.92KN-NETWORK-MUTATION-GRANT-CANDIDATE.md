# EA-4E.92KN network mutation grant candidate

Status: NON-LIVE BYTE-CONTRACT CANDIDATE / NOT AN ISSUER.
Parent: `39a07951cc694d5aa20bf6a330b51e058912a863`.

The first `network_create` mutation grant has a partial, pure C# candidate
byte verifier. Its canonical ASCII JSON schema binds the grant and nonce, store ID and
epoch, delegated attempt, request and predecessor hashes, source commit,
operator SID, Docker executable hash and endpoint, target network name,
issue/expiry times, and artifact hash. All independently supplied expected
fields must match. The verifier rejects a changed action, excess TTL,
altered identity, noncanonical bytes, and a recomputed hash over an invalid
scope. It has no store, Docker, shell, network, receiver, or model capability.

Qualification on the working tree:

- Focused 92KN: 21 passed, 0 failed.
- Adjacent 92I/92J/92K and owner checks: 479 passed, 0 failed.
- New files: `tools/Ea4eNetworkMutationGrantCandidate.cs`,
  `tests/hermes_core/fixtures/ea4e92kn_network_grant_probe.cs`, and
  `tests/hermes_core/test_ea4e92kn_network_mutation_grant_candidate.py`.

This is a partial candidate-data contract only, not the complete 92JU
artifact. In particular, it does not bind issuer identity, current authority
identity, labels/command-spec hash, or a durable one-attempt budget and
revocation state. The expected values in its API are not a trusted source by
themselves. It neither proves operator consent nor issues, persists, claims,
or consumes a real grant. A reviewed contract roll and store binding, the
protected issuer, independent expected-value source, store/anchor recovery,
exact approved binary installation, and action-specific live authorization
remain open.
No UAC, Docker mutation, Kilo/OpenCode invocation, model use, GPU,
ComfyUI, or production activation occurred. Production remains HOLD.
