# EA-4E.92KJ single-process operator/request preflight

Status: NON-LIVE CANDIDATE / NOT INSTALLED / NOT AN ISSUER.
Governing source: `54f8256fde8c864d1e9f1d823921f58ddb51fc6d`.

The 92KB Windows token observation and 92KI canonical network-request check
previously existed as separate programs. The new read-only entry point
checks the current process token's exact expected SID and elevation first,
then reads at most 16 KB from one exclusive request handle and passes those
bytes to the 92KI checker. It has no grant issuance, store, Docker action,
receiver/model invocation, or production activation capability. Its only
positive output is `MATCH:NON_AUTHORIZING_PREFLIGHT`.

The existing 92KB CLI retains its output contract after extracting the token
observation to an internal shared class. The 92JV request's `operator_id`
remains a candidate string independent of the observed Windows SID. This
preflight does not bind the two as a witnessed issuer identity. Caller-supplied
expected hashes, commit, Docker digest, attempt, network, and labels also
remain untrusted until obtained through the separately governed protected
ceremony. Running this candidate elevated from the writable worktree would
not satisfy the 92JY installation contract.

Current source SHA-256 values:

- `tools/ea4e_docker_operator_preflight.cs`:
  `46D1970615C50F93114E10E6E8E65F3CA747351A68E3C4D913EC9DDA80C5AABF`
- `tools/Ea4eNetworkIssuePreflightCandidate.cs`:
  `AD288904F40375829AAFFC54440BF8A04AB1458E108D82CC80631AE7E8342392`

The unchanged 92KI checker and its observed .NET dependencies remain part
of this candidate's uninstalled source closure. Focused 92KB/92KI/92KJ
tests passed 29/29. The adjacent EA-4E.92I/92J/92K fake-only suite plus
92HJ/92HV/92HY passed 457/457 before commit. Committed-tree verification
is still required. The positive elevated path was not exercised because the
current session is unelevated; no UAC prompt was issued. Wrong SID and
oversized request tests denied on this host.

No Docker mutation, receiver/model call, GPU, ComfyUI, or production
activation occurred. A protected install, independent expectation source,
operator/SID-to-request binding, distinct durable real issuer, action-specific
grant, and actual agent handoff remain open. Production remains HOLD.
