# EA-4E.92MM local app-host read-only observers

Status: NON-LIVE CANDIDATE / PRODUCTION HOLD.
Parent: `6971b5bd98b7d04c8e8d37ce51918b8b2f9a81b5`.
Scope: accepted local-container profile only; strict 92AT/92ME unchanged.

The existing Windows token reader now exposes the current process account
SID without requiring elevation. The 92ML adapter reads the durable
invocation-authorization store ID and generation together under its existing
coordination lock, using its database/anchor verification. A missing store,
missing reader, malformed SID, or unavailable observation denies through the
92ML gate. No store write, issuance, claim, consumption, Docker operation,
receiver launch, or model call is introduced.

An initial attempt to add a public atomic method to the shared durable-store
module was discarded after the broader gate showed two sealed EA-4E.23
contract-ID assertions. The shared module has no final worktree diff. The
atomic read instead lives in this versioned local-profile adapter and uses
the store's existing private verification methods. Those two tests still
fail after the shared module was restored; their historical expected ID is
`a64ec105...`, while the current computed ID is `2fac55b9...`. The
contract-computation source and its imported contract inputs have no changes
in this checkpoint. They are inherited/stale assertions, not new 92MM
behavior; no contract reseal is authorized by this slice.

Final focused token and local-gate tests: 32 passed. Broad adjacent run:
150 passed, 2 inherited contract-ID failures. The same broad run with those
two named historical assertions deselected passed 150/150. A read-only current Windows
token smoke returned `SID_READ_OK`; the SID was not recorded in evidence.

The account check trusts this app process under 92MK. A fake collaborator in
a test is not a production witness. The configured governing commit remains
an expectation, not independently attested loaded code. The adapter is not
yet wired into `app.py`. Protected Docker mutation issuance, bounded real
receiver/model proof, and activation remain separate and unauthorized.
