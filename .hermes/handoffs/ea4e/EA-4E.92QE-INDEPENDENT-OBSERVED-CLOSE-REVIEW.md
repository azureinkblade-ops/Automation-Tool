# EA-4E.92QE Independent Observed-Close Review

One separately approved, independent read-only reviewer inspected the eight
exact Git blobs in `EA-4E.92QE Observed Directory Handle Review Request.md`
at `d3e5ef72493322e8c32fd96179f0be675b8fe7d1`. All eight SHA-1 values
matched before substantive review. The attributable reviewer result is in
Codex thread `01a16067-fb9d-7091-8fb3-cc4f634a3727`.

## Findings

1. **High, existing issuer blocker.**
   `tools/Ea4eDirectory2OneAttemptCandidate.cs:52-84` moves from
   caller-supplied value screening to the native invocation. The pinned
   install plan checks path/descriptor consistency, not parent/manifest/SID
   provenance, ACL-capable volume, privilege, first-child absence, or actual
   client-token effective rights. No committed C# caller of `AttemptUnwired`
   was found. This is an unwired integration blocker, not evidence of a
   production exploit.
2. **Medium, post-create reconciliation is not explicit.** After a
   non-sentinel native return, shape or descriptor denial can close the
   handle successfully and return an ordinary readback denial. Closing the
   handle does not remove the newly created directory. The current output
   publishes file identity only on full readback success, so the denial
   neither signals mandatory reconciliation nor preserves any partial
   identity that was successfully observed. Catchable post-call exceptions
   are marked uncertain but do not retain object identity. Do not retry,
   adopt, or delete by path to compensate.

The reviewer found no concrete double-close or handle-reuse path in the
inspected synchronous, catchable-exception contract. It accepted the
source-level distinct wrapper-close uncertainty and separate native creation
and release error outputs. It noted that `ReleaseObserved == false` includes
both failed and not-yet-observed release. Widened `SafeHandle` reader
signatures retain SafeHandle marshalling and existing `SafeFileHandle`
compatibility, but permit unrelated handle subclasses at compile time.
Multi-call observation is not pinned against concurrent disposal; no bypass
was found in the private owner path. The native declaration agrees with the
documented five-argument ABI, but runtime ABI is unqualified.

Verdicts: source-only ownership/close correction **PASS within the inspected
synchronous contract**; complete one-attempt owner **HOLD**; native issuer
**HOLD**; strict 92AT mapped-byte invariant **REJECT**, unchanged. No claim of
production readiness follows. The reviewer did not run even the inert tests,
edit files, invoke native code or Docker, call a receiver/model, use
GPU/ComfyUI, or activate production.

Narrow next non-live action: make a post-create reconciliation result
unavoidable on every denied path after a non-sentinel return, preserve any
observed identity as explicitly partial, and keep readback, creation, and
close outcomes distinct. The revised source requires a new pinned review.
