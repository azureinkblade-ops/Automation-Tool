# EA-4E.92KW network request/grant binding

Status: NON-LIVE / PURE BYTE CHECK QUALIFIED. Not an issuer.
Baseline: `7cfe777a68e0d7c7b69a2b3cfd85b8f272283bab`.

`Ea4eNetworkRequestGrantBinding.Matches` requires both the canonical v1
network-create request and the canonical v2 grant to pass their existing
validators against the same externally supplied expected fields. It binds
the request hash, commit, Docker executable digest, attempt, operator SID,
network target, and four labels to the grant. The grant's issue-to-expiry
interval cannot exceed the request's requested TTL. The request validator
still requires every authorization flag to be false.

Focused tests: 11 passed, 0 failed. Adjacent EA-4E.92I/J/K and HJ/HV/HY
fake-only tests: 563 passed, 0 failed. Tamper cases cover individually valid
foreign grant identities, grant lifetime extension, a rehashed request with
an authority flag, noncanonical request bytes, and a foreign grant expectation.

The expected grant fields and labels in these tests are harness supplied.
This relationship check does not prove current authority, operator review,
protected issuer identity, trusted time, or protected store placement. It
has no Docker, receiver, model, GPU, or ComfyUI capability. Production HOLD.
