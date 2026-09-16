# EA-4E.92S Dedicated Probe Bootstrap - Partial Implementation

Date: 2026-09-16
Governing synchronized baseline:
`c7a51fcd483d4eed2ed49a88e201b87062939d3b`

State: IMPLEMENTED / REVIEWED / STAGED-EXPORT PASS / UNCOMMITTED

## Scope

Added one repository-owned Node bootstrap artifact for the frozen NQ-01 through
NQ-12 matrix. Its current immutable identity is 6,834 bytes, SHA256
`6884c8745ea18c9195736c48745816c0b8b8e3cbd0be966a089042e6e97df1b2`,
with repository-internal SPDX provenance.

The bootstrap has exact ordered CLI parsing, canonical request validation,
fixed budgets, probe-specific configuration validation, a four-byte
big-endian result-frame header and bounded canonical JSON result payload. It
fails closed on malformed identity, schema, budgets, targets or framing.
NQ-01 explicitly refuses resumed execution.

The existing value-only admission contract now binds `probeConfig` into both
the canonical request artifact and returned evidence. Network targets must be
literal IP addresses; NQ-04 requires loopback and NQ-05 rejects loopback,
unspecified and multicast targets. NQ-06/NQ-07 bind an absolute path and exact
SHA256. These checks bind reviewed values only and do not prove harness
ownership, ACLs or safe handle-relative access.

## Review Corrections

Initial focused qualification exposed no test failures, but source review found
two behavioral defects before broad qualification. An unresolved Promise alone
does not reliably keep Node alive, so NQ-08/NQ-12 now retain an active timer.
Filesystem probes now compare observed bytes to the reviewed target SHA256
instead of merely reporting a digest. The artifact identity above is for the
corrected bytes.

## Verification

Focused bootstrap plus admission contract: 89 passed / 0 failed / 0.18 seconds.
Complete bounded EA-4E.92S chain: 492 passed / 0 failed / 0.83 seconds. Both
runs reported process/network tripwire events 0 and filesystem events 0.

Complete guarded Hermes Core gate: 4087 passed / 35 raw inherited failures / 6
unchanged deselections / 104 subtests passed, exit 1, 124.19 seconds. Exact
failure-identity comparison with the committed probe-admission baseline found
35 versus 35, added 0, missing 0, exact match. All 32 attempted process
launches were denied; filesystem events 0. JUnit SHA256:
`a364a731737821412a77ae95f67f253247e9381ef41374c84b4953a05939c07e`.

## Boundary

The JavaScript artifact was never imported, parsed by Node or executed. No
native process, suspended thread, child, socket, filesystem probe, allocator,
timeout, overflow, parser, receiver, model, browser, GPU or ComfyUI action ran.
Static Python tests only inspected repository bytes and source markers.

The dedicated bootstrap identity closes the artifact-absence portion of Stage
3 blocker 1. It does not authorize a launch. Existing profile/ACL suitability,
exact harness-owned target fixtures, native adapters, race-safe staging,
durable evidence storage and broker-death reconciliation remain open. Native
containment remains NOT QUALIFIED.

## Staged Export Qualification

The first index export exposed a line-ending identity mismatch: without an
explicit Git attribute, the reviewed 6,834-byte LF artifact was archived as a
7,056-byte CRLF artifact with a different SHA256. Added one path-specific
`.gitattributes` rule (`text eol=lf`) and rebuilt the index. No broad line-ending
policy changed.

Corrected immutable export `.ea4e92s-bootstrap-index-b.zip` SHA256:
`40d7e6dbb9b3f4eb5d3be68e0401da39139234482498d8d98422a8b2c1cdc7d3`.
The exported bootstrap is exactly 6,834 bytes with SHA256
`6884c8745ea18c9195736c48745816c0b8b8e3cbd0be966a089042e6e97df1b2`.
The extracted index tree passed the complete 492-test bounded chain with
process/network and filesystem tripwire counts zero.

Exactly six files belong to this checkpoint: the narrow attribute rule,
bootstrap artifact, static bootstrap test, admission source, admission tests
and this evidence file. No tracked file is unstaged. No commit or push has
occurred.
