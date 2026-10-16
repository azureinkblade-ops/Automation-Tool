# EA-4E.92KQ network-grant v4 digest component

Status: NON-LIVE PURE DIGEST / NO STORE TRANSITION OR ISSUER.
Parent: `f25c4ad5cbb29544d6faf10f92dac6d6a3fcd4f8`.

This slice implements a deterministic, domain-separated row digest over
grant ID, exact bounded ASCII artifact bytes, and current mutable state.
The table digest sorts rows by grant ID, rejects duplicate IDs, and binds
the row count plus every row digest. The row snapshots input bytes, so a
caller changing its buffer after construction cannot alter the result.
Allowed state labels are `ISSUED`, `CLAIMED`, `REVOKED`, and `UNCERTAIN`.

Focused tests: 12 passed, 0 failed. Adjacent 92I/92J/92K and owner
checks: 515 passed, 0 failed on the working tree. Changed files are the
new `tools/Ea4eNetworkGrantV4Digest.cs` and two focused test files.

This component does not parse or validate v2 grant semantics, issue a grant,
read/write SQLite, publish an anchor, or call Docker. A future v4 store must
separately run the 92KO byte verifier at issuance, bind the digest into each
journal generation and anchor, and reject artifact/row-ID mismatch on reopen.
The 92KP v4 store design remains a candidate, not an accepted real issuer.
No UAC, Docker mutation, receiver/model call, GPU, ComfyUI, or production
activation occurred. Production remains HOLD.
