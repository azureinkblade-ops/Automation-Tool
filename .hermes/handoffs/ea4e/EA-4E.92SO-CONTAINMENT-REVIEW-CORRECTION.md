# EA-4E.92SO containment review correction

Date: 2026-10-26

The one approved independent read-only review of pinned source commit
`1f73699d46d802139249e87b7e60b7369b3d7142` returned HOLD. Its concrete
finding: the containment-check tuple evaluated all expressions before the
first failure was examined. A malformed later inspect field could therefore
raise a generic exception instead of reporting the first fixed label. The
reviewer made no edits, tests, Docker, Ollama, model, GPU, receiver, or
handoff call. That one-review approval is consumed.

The source-only successor evaluates each check lazily in order. A malformed
value in the current check is converted to a fixed, code-owned denial label;
the observed value is never interpolated. The existing containment
predicates, pre-start denial, and exact-owner cleanup remain. New fake tests
cover a malformed later field after an earlier mismatch and a malformed
current field. The focused strict non-live suite passed 43/43. No native
run followed this correction.

The corrected committed blob requires a new independent source-only review.
Any native tags-only diagnostic also requires a fresh exact one-shot
authorization. The empty-`manifests-v2` hypothesis remains untested.
Production remains HOLD.
