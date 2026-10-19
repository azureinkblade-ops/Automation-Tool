# EA-4E.92NS protected grant candidate ledger

Status: NON-LIVE CANDIDATE LEDGER QUALIFIED / PRODUCTION ISSUER HOLD.
Parent: `6648defe5406a933ae7e5a9ea600573f16656a7b`.

This adds a distinct `hermes.docker-network-grant-store/protected-v2`
ledger and `hermes.docker-network-grant-row/protected-v2` row digest.
The fake v4 ledger and protected-v1 zero-generation bootstrap are unchanged.
There is no migration or cross-open between the three schemas.

The candidate ledger accepts only the protected-v1 canonical grant bytes
under independently supplied expected values. Its `IssueCandidate`,
`ClaimCandidate`, `RevokeCandidate`, and `MarkUncertainCandidate` methods
persist single-attempt state and bind row-table digests, journal generations,
and append-only anchor files. Reopen denies modified rows, schema drift,
missing anchors, database-only rollback, and a post-commit/pre-anchor gap.
Simultaneous duplicate issuance has one winner. A claimed grant cannot be
claimed again; revoked and uncertain states persist.

Focused candidate-ledger matrix: 21 passed, 0 failed. Combined protected
grant parser, protected-v1 bootstrap, fake v4 ledger, and fake candidate
regression: 94 passed, 0 failed. Tests use an inert C#
probe and the local SQLite library; no Docker or receiver call exists in
the new production modules.

This is **not** an issuer. The probe supplies the expected fields itself;
it does not witness the operator, binary, installation, current authority,
or governing commit independently. The ledger has no installed path/ACL
qualification and no externally protected high-watermark against coherent
database-plus-anchor rollback. Under the separately accepted 92DE local
profile, trusted administrators/app host are part of the TCB; the strict
administrator-inclusive 92AT/92CZ profile remains REJECT/HOLD. No actual
protected grant was issued for a Docker mutation, and no native pipe, UAC,
Kilo/OpenCode/Codex receiver, model, GPU, ComfyUI, or production activation
was run.
