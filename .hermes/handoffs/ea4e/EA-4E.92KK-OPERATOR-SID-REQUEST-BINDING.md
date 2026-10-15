# EA-4E.92KK operator SID/request binding

Status: NON-LIVE CANDIDATE CORRECTION / NO ISSUER.
Governing source: `a5278db9a360d9866d9448f3cd40fb86e47f54a4`.

The initial 92KJ preflight observed the Windows token SID but allowed a
different request `operator_id`. The composite now denies unless the
operator candidate passed to the byte checker exactly equals the expected
SID passed to token observation. The token observation checks that SID
against the current process token. The 92KI byte checker then requires the
canonical request's `operator_id` to equal the same candidate. A request
carrying an unrelated operator label therefore cannot pass the combined
check, even when its own request hash is valid.

The 92JV pure request builder still accepts an unverified candidate string;
this change does not grant its output authority. The expected SID and other
expected inputs remain caller-supplied to this uninstalled candidate. A
protected issuer must derive them from an independently reviewed ceremony,
pin its source/runtime closure, and bind durable store/attempt authority.
The current unelevated process cannot exercise the elevated positive path.

Current `tools/Ea4eNetworkIssuePreflightCandidate.cs` SHA-256:
`5F093230D63773711A6D82AB6C4ADDAF6E704BEFCB33BD7A7BB41D23FFB89707`.
Focused 92KB/92KI/92KJ tests passed 30/30. The adjacent fake-only
EA-4E.92I/92J/92K plus 92HJ/92HV/92HY suite passed 458/458 before commit.
Committed-tree rerun is still required. No UAC, Docker mutation, receiver or
model call, GPU, ComfyUI, or production activation occurred. Production
remains HOLD.
