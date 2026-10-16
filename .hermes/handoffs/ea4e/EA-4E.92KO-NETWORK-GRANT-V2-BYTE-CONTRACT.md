# EA-4E.92KO network-create grant v2 byte contract

Status: NON-LIVE CANDIDATE / NO ISSUANCE OR SPEND.
Parent: `b800971dca2baeff9fea04a288a9811aa9c92042`.

The 92KN v1 partial candidate remains intact. A second, versioned pure
verifier checks the proposed `network_create` v2 immutable candidate. It
adds issuer-binary and ceremony identities, current authority identity,
the exact four network labels, internal bridge policy, a command-spec hash,
an initial `ISSUED` marker, and a one-attempt budget. For this first action,
`command_spec_hash` must equal the canonical 92JV request hash, which binds
the network-create argv, labels, and policy. This equality is a candidate
contract decision, not a grant of authority.

The verifier requires independent expected values for every variable
identity, time, and label. It rejects cross-action reuse, stale/mismatched
expected identities, altered network scope, a second-attempt budget,
noncanonical bytes, and invalid TTL. A focused integration case constructs
the candidate from the existing 92JV request fields. The C# module itself
has no store, filesystem write, Docker, process launch, network, receiver,
or model capability.

Qualification on the working tree:

- Focused 92KN + 92KO: 45 passed, 0 failed.
- Adjacent fake-only 92I/92J/92K and owner suite: 503 passed, 0 failed.
- Changed production file: `tools/Ea4eNetworkMutationGrantCandidate.cs`.
- Added test files:
  `tests/hermes_core/fixtures/ea4e92ko_complete_network_grant_probe.cs` and
  `tests/hermes_core/test_ea4e92ko_complete_network_grant_candidate.py`.

The candidate still cannot establish independent issuer or operator
identity. `state_at_issue` is not current revocation/cancellation state;
the future issuer and claimant must query and atomically update the
protected store. The store schema does not yet persist every v2 field or
artifact hash, and no real grant exists. Protected binary installation,
store/anchor crash recovery, an independent UAC ceremony, current authority
verification, real one-shot issuance/claim, and a separately bounded Docker
mutation remain open. No UAC, Docker mutation, Kilo/OpenCode/model call,
GPU, ComfyUI, or production activation occurred. Production remains HOLD.
