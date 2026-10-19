# EA-4E.92MV pure issuer-policy byte contract

Status: NON-LIVE CANDIDATE / NOT AN ISSUER / PRODUCTION HOLD.
Parent: `d0b5f945e5dc68cd9397d62f169f105c6b186b8a`.

`Ea4eProtectedIssuerPolicyCandidate` accepts bounded canonical ASCII JSON
and an externally supplied SHA-256 expectation. It fixes schema v1, local
protected-issuer profile, `network_create`, local Docker endpoint, TTL at
most 300 seconds, and one-attempt budget 1. It validates the required
operator/app SIDs, source/authority/store/executable identities, canonical
local paths, common issuer/policy/dependency directory, common store/anchor
directory, and distinct file roles. Extra/missing fields, fake profile,
foreign action, invalid paths, noncanonical bytes, and a matching hash over
invalid scope deny.

Changed files: `tools/Ea4eProtectedIssuerPolicyCandidate.cs`,
`tests/hermes_core/fixtures/ea4e92mv_issuer_policy_probe.cs`, and
`tests/hermes_core/test_ea4e92mv_issuer_policy_candidate.py`.

Working-tree qualification: 66 passed / 0 failed across the policy parser,
native token and image witnesses, protected grant bytes, and v5 store.
Only local compiler/test-probe processes ran. No protected installation,
policy publication, UAC, Docker mutation, receiver/model, GPU/ComfyUI, or
production activation occurred.

The test harness supplies the expected policy hash. The parser neither reads
a protected installation nor proves that an operator independently approved
the hash. File ownership, effective ACL, ancestor/reparse, dependency bytes,
actual current token/image, app-instance identity, trusted clock, v5 store
bootstrap, and request/authority binding remain separate gates. It must not
be loaded into an elevated issuer from this worktree. Strict 92AT remains
REJECT/HOLD; the accepted local profile is distinct.
