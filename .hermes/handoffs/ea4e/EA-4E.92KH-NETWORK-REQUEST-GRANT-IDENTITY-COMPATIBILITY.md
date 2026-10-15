# EA-4E.92KH network-request/grant identity compatibility

Status: NON-LIVE / FAKE-ONLY CONTRACT CORRECTION.
Governing source: `61f14165ad173400557b438d8b1ecffa22de31cb`.

The existing 92JV network-create request requires a 64-hex governing
identity and carries delegated attempt IDs such as `attempt-1`. The 92KE
fake grant store incorrectly required a 40-hex source value and a 64-hex
attempt ID. This checkpoint accepts the request's 64-hex governing identity
and bounded ASCII attempt-token shape. Grant IDs, grant nonces, request and
predecessor hashes remain 64-hex. The candidate operator SID is deliberately
separate from the request's unverified `operator_id`.

An integration test takes the existing 92JV builder's actual request and
uses its attempt ID, request hash, and governing identity as inputs to the
isolated C# fake grant probe. It passes without rewriting those identities.
Tests also deny a 40-hex source value and whitespace in an attempt ID.
The candidate source SHA-256 is
`F1C8ACDF479EF273B701411D4683D0A9F0FCD265669BC08BCA62A6357EE2D9C9`.

Focused 92KE tests passed 23/23 and the adjacent fake-only 92I/92J/92K
ladder passed 434/434 before commit. Committed-tree verification remains
required. This does not establish that the supplied SID, clock, request
hash, source identity, or Docker executable came from an independent
operator or protected installation. No UAC, Docker mutation, receiver/model
call, GPU, ComfyUI, or production activation occurred. Production remains
HOLD.
