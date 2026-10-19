# EA-4E.92MQ protected issuer contract-roll design

Status: NON-LIVE DESIGN / PRODUCTION HOLD.
Parent: `2d68024cc445aedb0f7947b7dcf4e4fa1d9d80cd`.
Scope: first `network_create` action under the accepted 92DE local-container
profile. Strict 92AT remains unchanged and rejected on mapped-byte proof.

## Discovered incompatibility

The current complete candidate parser fixes schema
`hermes.docker-network-mutation-grant-candidate/v2` and label
`hermes.ea4e.profile=FAKE_ONLY_LOCAL_CONTAINER`. The v4 store verifies
those bytes and exposes `IssueFake`, `ClaimFake`, `RevokeFake`, and
`MarkUncertainFake`. Neither that schema nor that store may become a
production issuer by changing a caller flag or method name. The existing
test probes accept expected fields from their own command line, which is
also not an independent operator witness.

## Required side-by-side roll

1. Define a distinct production grant schema and label for exactly
   `network_create`. Preserve the fake v2 schema and v4 store unchanged.
   The production verifier must reject fake v2 bytes, a fake profile label,
   any other action, extra/missing fields, noncanonical bytes, or recomputed
   hashes over invalid scope.
2. Bind the production grant to issuer binary identity, installation and
   store ID/epoch, operator SID and elevation, governing source commit,
   delegated attempt and current authority, exact request/predecessor hash,
   Docker executable digest/endpoint, deterministic target name/labels,
   issuance/expiry, cancellation or revocation state, and one-attempt budget.
   The issuer must source expected values from independently reviewed
   protected policy, not the app request or the grant being checked.
3. Define a new production store schema and anchor lineage. Do not open a
   v4 fake store as a production store or migrate its grants. Issue, claim,
   revoke, and uncertain transitions must be durable, append-only and
   non-retryable after ambiguous commit/anchor publication. Reopen/replay
   must not restore a spent budget. No Docker call belongs in the issuer.
4. Build the self-contained native issuer closure with the 92MO token and
   92MP file-image witnesses, plus independently qualified protected-path
   ownership, effective ACL, reparse, transitive dependency, and policy
   checks. The 92MP disk hash is not mapped-image-byte proof. A qualified
   installation and UAC ceremony need a separate exact authorization.
5. Qualify fake-only negative tests for wrong profile/schema/action,
   malformed bytes, operator, binary, source and store drift, duplicate
   issuance, concurrency, expiry, revocation, rollback, and crash gaps.
   Only after that review may one exactly bounded real `network_create`
   authorization be proposed. Gateway and receiver actions remain separate.

No production schema/store is implemented by this design. No installation,
UAC, Docker mutation, Kilo/OpenCode/model call, GPU/ComfyUI use, or production
activation is authorized or performed.
