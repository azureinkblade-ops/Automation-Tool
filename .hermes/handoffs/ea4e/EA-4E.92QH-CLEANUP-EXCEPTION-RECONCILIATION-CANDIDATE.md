# EA-4E.92QH Cleanup-Exception Reconciliation Candidate

The independent 92QG review found that a catchable `Dispose()` exception in
the unwired directory owner could escape its outer `finally` before the
post-attempt reconciliation disposition was selected. This source-only
candidate catches that cleanup exception, records wrapper-close uncertainty,
and continues to the existing `ClassifyDisposition` gate. A pre-wrapper raw
close is marked uncertain before `CloseHandle` is called, so a thrown close
cannot be mistaken for an unattempted release. Neither close is retried.

Focused inert owner tests passed 17/17. The adjacent source-only matrix
passed 113/113. These tests cover source structure, pure classification,
pre-call screens, and invalid handles; they do not exercise a valid native
handle or prove an actual thrown-close outcome. The corrected blob still
requires a new, independent, pinned review. The 92QG review authorization
was consumed on the prior source.

The source owner, authenticated native issuer, effective client rights, and
real Kilo/OpenCode handoff remain HOLD. The strict 92AT mapped-byte invariant
remains REJECT. No native creation, Docker mutation, receiver/model call,
GPU, ComfyUI, or production activation occurred in this checkpoint.
