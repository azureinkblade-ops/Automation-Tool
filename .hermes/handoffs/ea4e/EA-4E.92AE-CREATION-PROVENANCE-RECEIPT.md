# EA-4E.92AE Creation Provenance Receipt

## Disposition

Non-live, value-only first implementation slice of the EA-4E.92AD
suspension-proof contract roll. It does not replace the current pre-resume
verifier and does not prove that a native `CreateProcessW` call happened.

## Contract

- The exact in-memory `OwnedSuspendedProcess`, creation owner, request ID,
  adapter hash, job handle, process/thread handles, PID/TID and exact required
  creation flags must agree with the canonical creation result.
- Required flags are exactly `CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT`;
  missing, extra or malformed flags deny.

EA-4E.92AO subsequently rolls this historical two-flag requirement to
include `CREATE_UNICODE_ENVIRONMENT` for the planned explicit Unicode
environment. See `EA-4E.92AO-UNICODE-ENVIRONMENT-FLAG-CONTRACT-ROLL-DESIGN.md`.
- Closed ownership, creation attribute drift, cross-request replay and
  conflicting resource identities deny.
- The receipt is an untrusted value until a separately reviewed native
  creation adapter and same-owner one-shot resume gate establish its origin.
  Neither component is implemented by this checkpoint.

## Working-Tree Verification

- Focused receipt and immediate owner/pre-resume tests: 121 passed.
- Complete EA-4E.92S through 92AE bounded gate: 740 passed.
- Bounded fake-only and filesystem tripwire events: 0 / 0.
- Guarded Hermes Core: 4,361 passed, 35 inherited failures, 6 deselected,
  104 subtests passed; fake-only denied 32 process attempts and filesystem
  tripwire events were 0.
- Failure identities versus committed 92AC baseline: 0 added / 0 missing.
- Full-suite JUnit SHA-256:
  `2126af66c2f610b3fb6c7edb423110dc84ceb0e0f21dec020fddee61c235382d`.

## Boundary

No native launcher, OS query adapter, resume operation, production wiring,
real process, receiver/model invocation, GPU or ComfyUI operation is added or
authorized. A fake-only receipt is not a positive pre-resume verdict or
production readiness. The next contract-roll slice must separately bind a
reviewed creation adapter, exclusive lifecycle owner and one-shot resume
authority before changing `ea4e92s_pre_resume.py`.
