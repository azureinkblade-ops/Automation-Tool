# EA-4E.92S Probe Target-Fixture Contract - Partial Implementation

Date: 2026-09-16
Governing synchronized baseline:
`e030663c604bbd83bd97541bdaa4b964d3193d34`

State: IMPLEMENTED / REVIEWED / STAGED-EXPORT PASS / UNCOMMITTED

## Scope

Added a value-only contract for the NQ-04/NQ-05 network targets and NQ-06/NQ-07
filesystem fixtures. It performs no path inspection, file access, listener
creation, socket operation or native call.

Network fixtures bind exact probe ID, literal IP, address family, high-range
port, listener ID, listener nonce SHA256, harness ownership and zero accepted
connection budget. NQ-04 requires loopback. NQ-05 requires an RFC1918 IPv4 or
ULA IPv6 address and rejects loopback, unspecified, multicast, public and
documentation-only addresses. Listener ports, IDs and nonces must be distinct.

File fixtures bind exact probe ID, artifact path/size/SHA256, fixture-root
volume/file identity, no-reparse state, harness ownership and expected
readability. The allowed file must be inside the exact request root. The
forbidden file must be under the exact harness root but outside request and
profile roots. Harness, request and exact profile snapshot identities are
bound; harness and profile roots must be disjoint.

## Composition Review

Initial focused qualification passed 32 cases. Review found that a valid target
policy was not yet cryptographically tied to the four admission records. The
validator now requires exact `ProbeAdmissionEvidence` for NQ-04 through NQ-07,
matching request ID, request-root volume/file identity, profile name/SID and
canonical probe-config SHA256. Missing, duplicate, forged or drifted evidence
is denied.

A second review replaced the profile path string with the complete existing
`ProfileSnapshot`. A final review added bidirectional harness/profile root
disjointness. Test-fixture corrections for a trailing Windows root literal and
an earlier canonical-path rejection changed no production assertion.

## Verification

Final focused target contract: 42 passed / 0 failed. Complete bounded
EA-4E.92S chain: 534 passed / 0 failed / 0.88 seconds. Process/network and
filesystem tripwire counts were zero.

Complete guarded Hermes Core gate: 4129 passed / 35 raw inherited failures / 6
unchanged deselections / 104 subtests passed, exit 1, 107.58 seconds. Exact
failure-identity comparison with the committed bootstrap baseline found 35
versus 35, added 0, missing 0, exact match. All 32 attempted process launches
were denied; filesystem events 0. JUnit SHA256:
`562bc3bf46f23fea6f08df113371500250e3b759a8d90c39ef9891ea63c4ee13`.

## Boundary

This checkpoint defines reviewed target identities only. It does not prove
that a listener is bound by the harness, that an address belongs to the host,
that a file exists with the reviewed bytes, that ACLs produce the expected
denial/allowance, or that handle-relative race protection is active. Those are
native preflight and execution boundaries.

No process, listener, socket, filesystem fixture, profile mutation, parser,
receiver, model, browser, GPU or ComfyUI operation occurred. Native probes
remain unauthorized and native containment remains NOT QUALIFIED.

## Staged Export Qualification

Staged exactly the value-only target contract, its focused tests and this
evidence file. Whitespace validation passed and no tracked file is unstaged.

Immutable export `.ea4e92s-targets-index-a.zip` SHA256:
`3351e5a49d81cb91afe178bb2032dcca284c6fe983862bf95e651f46d006e482`.
The extracted index tree passed the complete 534-test bounded EA-4E.92S chain
with process/network and filesystem tripwire counts zero. No commit or push has
occurred.
