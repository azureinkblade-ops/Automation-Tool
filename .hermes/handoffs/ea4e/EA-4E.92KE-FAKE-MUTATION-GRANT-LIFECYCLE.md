# EA-4E.92KE fake Docker-mutation grant lifecycle

Status: NON-LIVE / FAKE-ONLY / NO OPERATOR WITNESS OR DOCKER PERMIT.
Governing source: `99a2784afd781e88bbfdc0b9bfd76c5724d14fc1`.

This checkpoint extends the 92KD candidate from store schema v1 to v3.
Schema v2 was transient uncommitted work; no v2 checkpoint or production
database exists. v3 has a separate fake-grant table with unique grant ID,
nonce, and (attempt ID, action). Each issue, claim, or pre-claim revocation
updates the grant row and one audit generation in the same `BEGIN IMMEDIATE`
transaction. The journal event binds a digest of all current grant rows; the
metadata and every generation anchor bind the corresponding journal state.
Reopen recomputes the grant-row digest. A changed `CLAIMED` row cannot be
presented as an unspent `ISSUED` row by editing SQLite alone.

Only four action names are recognized: `network_create`, `gateway_create`,
`gateway_start`, and `kilo_container_create`. Exact duplicate issue and
conflicting nonce or attempt/action are denied. Claim requires exact grant,
action, attempt, request and predecessor hashes and a time inside the bounded
issue/expiry interval. A claimed grant cannot be claimed again or revoked back
to an unspent state. An uncertain outcome after claim is non-retryable.

Source SHA-256 at qualification:

- `tools/Ea4eDockerMutationStoreIdentity.cs`:
  `12774C85F495C5D3CA6DD35A98D36EE56A0D4B9499A27FDE9E59A57DC7B5539A`
- `tools/Ea4eFakeDockerMutationGrants.cs`:
  `4EAD12EC723F5F659ED850ACDC835050CC374F7DFF5D57B5F326DC7CF164D493`

The focused 92KD/92KE set passed 28/28. It covers duplicate issue,
concurrent issue with one winner, nonce/attempt conflict, wrong scope/time,
revocation, replay denial, invalid inputs, and direct grant-row tamper.
The adjacent fake-only 92I/92J/92K/HJ/HV/HY ladder passed 429/429 before
commit. Committed-tree requalification remains required.

This is not a production issuer. The test API accepts a SID, clock values,
source commit and request hash as caller data; it does not verify an elevated
operator, active authority, canonical request, Docker executable, or protected
installation. No immutable signed/witnessed permit or action-specific real
claim exists. Store/anchor placement and crash-gap reconciliation are not
qualified. There is no Docker/process/network/receiver/model capability in
the candidate class. No UAC, Docker mutation, Kilo/OpenCode call, GPU,
ComfyUI, or production activation occurred. Production remains HOLD.
