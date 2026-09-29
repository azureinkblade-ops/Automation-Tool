# EA-4E.92BB Retain Exact Mapped-Byte Requirement

## Decision

On 2026-09-29 the user explicitly chose to retain the exact EA-4E.92AT
post-create, pre-resume mapped-image byte requirement. This decision is
bound to the synchronized EA-4E branch at
`7089665219cbdc92774391852d7976484c743413` and the independent
staging review in
`EA-4E.92BA-INDEPENDENT-STAGING-PROOF-REVIEW.md`.

The review's exact byte-invariant finding is `REJECT` on the available
evidence. Trusted image binding and trusted native creation remain
`HOLD`. A staged file's path, file ID, or flat-file SHA-256 is not a
substitute for proof of the executable image section's bytes.

The user also explicitly rejected treating Windows App Control's
Authenticode/PE image hash as equivalent to the 92AT measurement. Its
hash algorithm is a different measurement; it does not close the
reviewed image-section byte-proof gap. No weaker file-provenance-and-
containment contract or design is authorized by this decision.

## Consequence

Do not relax, rename, or bypass `VERIFIED_SUSPENDED` or the 92AT byte
invariant. Do not implement a positive native creator path, roll debug
creation flags, conduct a native/live probe, invoke a receiver/model,
use GPU/ComfyUI, or activate production on the basis of the 92BA
review or this decision. Fake-only policy tests cannot establish the
Windows loader byte invariant.

The next permitted work is bounded, non-live research for authoritative
evidence that directly closes the exact section-source-byte gap under
the frozen threat model. Any proposed method must receive independent
review and separate implementation and live authorizations. If no such
method is found, the HOLD persists. A future weaker contract would
require a new explicit user decision; this record grants none.

`EA4E92BB_ARCHITECTURE_DECISION=RETAIN_EXACT_92AT_BYTE_REQUIREMENT`

`MAPPED_BYTE_INVARIANT_ON_AVAILABLE_EVIDENCE=REJECT`

`WEAKER_CONTRACT_DESIGN_AUTHORIZED=NO`

`TRUSTED_IMAGE_BINDING_QUALIFIED=NO`

`TRUSTED_NATIVE_CREATOR=HOLD`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
