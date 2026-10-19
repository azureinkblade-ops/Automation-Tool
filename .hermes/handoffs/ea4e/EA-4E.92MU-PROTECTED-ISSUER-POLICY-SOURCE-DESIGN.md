# EA-4E.92MU protected issuer policy-source design

Status: NON-LIVE DESIGN / PRODUCTION HOLD.
Parent: `6fb384c418c2d135f6fbd7072159566b65caaed2`.
Profile: accepted 92DE local-container profile only. Strict 92AT remains
REJECT/HOLD and is not repaired by this design.

## Authority split

The ordinary app may supply a delegation request and a proposed Docker
`network_create` specification. It may not supply a trusted `verified` flag,
operator witness, issuer image identity, store anchor identity, governing
commit, or production grant. `BuildProtectedCandidate` and v5
`IssueProtected` are pure lower-level components; calling either with
app-derived expected values is not an issuance ceremony.

The approved operator must review a versioned native issuer executable and
its full build/dependency closure, plus a canonical policy file. The exact
binary and policy SHA-256 values must be recorded through an independent
approval channel. A separately authorized elevated installer copies inert
bytes to a new protected versioned directory, verifies destination hashes,
owner/effective ACL and every ancestor/reparse boundary, and never imports
or executes source from the worktree. No in-place overwrite is allowed.

The candidate policy is one exact-action record with these mandatory fields:

| Field | Required source and check |
| --- | --- |
| profile, schema, action | Fixed protected schema, local-container profile, `network_create` only |
| issuer path, executable SHA-256, dependency manifest hash | Independent operator review plus protected installed-byte observation |
| policy path, policy SHA-256, installation version | Independent operator review plus protected installed-byte observation |
| operator SID and elevation | Native current-token observation in the elevated issuer; match policy SID |
| app SID and app-instance identity | Separately qualified local-profile app-host admission; never infer from the issuer's elevated token |
| governing commit and authority ID | Reviewed committed source and current Hermes authority evidence, not app text alone |
| store path, anchor prefix, store ID, epoch | Protected v5 bootstrap record and expected identity; no v4 migration |
| Docker executable SHA-256 and engine endpoint | Protected policy and fresh local observation; endpoint fixed to the reviewed local engine |
| attempt ID, request/predecessor hash, target network name/labels | Recompute from canonical delegated request and current authority; exact one-action match |
| issued/expiry and one-attempt budget | Independent issuer clock, bounded TTL, one durable v5 claim |

The policy hash cannot be established by a hash read from the same mutable
app request. The installed issuer must fail closed on missing or changed
policy, binary, dependency, operator, app-instance, source, store, or Docker
identity. The operator's UAC confirmation is one explicit ceremony and does
not authorize Docker mutation by itself. The v5 claim must precede exactly
one mutation attempt; an ambiguous commit/anchor result stops without retry.
Cancellation and revocation before claim deny; after claim, outcome must be
recorded as success, failure, or uncertain without restoring the budget.

## Qualification sequence

1. Freeze the canonical policy schema and pure negative parser tests, with
   independent expected policy hash supplied only by a test harness.
2. Build and inspect the complete native issuer binary/dependency closure;
   test that the app request cannot override policy values. Do not install.
3. Qualify protected path, owner, ACL, reparse, and installed-byte checks
   against a separately approved inert fixture. Do not infer authority from
   the current worktree or current token.
4. Request a new exact authorization naming the installer, source/destination
   hashes, destination path, operator SID, v5 store identity/epoch, timeout,
   and rollback plan. Installation and UAC are not authorized here.
5. Only after installation review may a separate one-shot `network_create`
   authorization be proposed. Gateway/container and real Kilo/OpenCode
   requests each require distinct bounded authority.

No file installation, ACL change, UAC prompt, Docker mutation, Kilo/OpenCode
receiver/model call, GPU/ComfyUI use, or production activation occurred.
