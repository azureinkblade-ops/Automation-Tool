# EA-4E.92BA Independent Staging-Proof Review Request

## Authority and Binding

This is a request for an independent, read-only review of the 92AZ
private fresh-file staging candidate. It is not a favorable verdict or
authorization to implement. Review committed baseline
`5732a522835ae19c09cb46fb14ba9a2c36625f21` on
`feature/ea4e67-kilo762-roll`. Verify these Git blobs first:

| Governing file | Blob SHA-1 |
| --- | --- |
| `.hermes/handoffs/ea4e/EA-4E.92AT-NATIVE-IDENTITY-AND-CREATOR-OWNER-DESIGN.md` | `5b3388c4cb9e7b4fa3b7c22753005fcf765dbb38` |
| `.hermes/handoffs/ea4e/EA-4E.92AY-INDEPENDENT-WINDOWS-IDENTITY-REVIEW.md` | `0ec838ef440bbd96e7456508efca9f8574b420cc` |
| `.hermes/handoffs/ea4e/EA-4E.92AZ-MAPPED-IMAGE-PROOF-OPTIONS-REVIEW.md` | `5d96907cb6c08f9b79c7cfdadd529acc2842edc2` |

If any blob differs, stop and report the mismatch. The reviewer must be
independent of the 92AZ author. No real Windows path/object inspection,
native call, process/fixture launch, receiver/model invocation, GPU,
ComfyUI, production activation, or source mutation is in scope.

## Exact Review Question

Can private fresh-file staging, under a precisely stated local threat
model, establish 92AT's post-create/pre-resume claim that the executable
image section represents the reviewed bytes? Do not replace that claim
with matching path, matching file ID, or SHA-256 of a later file read.
92AY's Q2 REJECT is the starting point, not something this request
overrules.

## Required Findings

Return separate `PASS`, `HOLD`, or `REJECT` decisions, with primary
Windows documentation or authoritative source citations, for:

1. **Freshness:** Does `CREATE_NEW` inside a protected directory prove a
   new file object with no prior image/writable section? State hard-link,
   alternate-stream, volume, and privileged-actor assumptions.
2. **Write exclusion:** Give exact creation-time ACL, handle access,
   sharing, file-close/retention, and process-create compatibility rules.
   Can an existing writer or mapping survive this sequence? Can an
   exclusive open interfere with the loader's access? Unsupported flag
   combinations or assumed behavior are HOLD.
3. **Namespace binding:** Show how a retained staged-file handle binds
   `CreateProcessW`'s path lookup despite ancestor reparse, DOS-device,
   mount-point, rename, and replacement races. State the exact fail-closed
   observation available after creation.
4. **Mapped-byte binding:** Identify the documented mechanism, if any,
   that proves the created image section corresponds to the reviewed
   staged bytes rather than merely to the same file object. Explicitly
   address pre-existing sections, copy-on-write image behavior, and
   section-versus-file content. If no mechanism is found, keep HOLD or
   REJECT; do not infer it from a fake test.
5. **Contract impact:** Explain how staging changes the reviewed runtime
   path/hash/file-ID pins, five-path inspector, exact creation flags,
   debugger lifecycle, one-attempt accounting, and cleanup. Distinguish
   an implementable source-only policy from a new architecture contract.

## Required Output

Produce an attributable review artifact with reviewer identity/date,
verified baseline and blob table, threat model, five findings, one
overall disposition for the **92AT byte invariant**, and the narrowest
next non-live action. Cite exact source/line references and direct
primary-documentation URLs. Label documented facts, inferences, and
unverified host behavior separately. Record whether any prohibited
action occurred (expected: none).

An overall PASS would qualify only a proposal for a separately governed
source-only implementation; it would not authorize a native process or
production activation. If the 92AT byte invariant cannot be supported,
state that clearly. A weaker file-provenance security claim requires a
separate explicit architecture decision and may not be smuggled into
`VERIFIED_SUSPENDED`.

`EA4E92BA_REVIEW_REQUEST_READY=YES`

`INDEPENDENT_STAGING_REVIEW_RECEIVED=NO`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
