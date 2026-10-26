# EA-4E.92SP Docker traceback correction

Date: 2026-10-26

The one approved independent read-only review of pinned commit
`e8edc1fe7af429aa832884ff5cc320f8410e8929` returned source HOLD. It
confirmed ordered fail-closed containment checks but found that an invalid
Docker output decode could render daemon-supplied bytes through Python's
exception chain. The reviewer made no edit, test, Docker, Ollama, model,
GPU, receiver, or handoff call. That one-review approval is consumed.

The source-only successor suppresses exception context on fixed-output
failures and converts non-ASCII create and interface responses to fixed
denials. It retains exact-owner reconciliation and cleanup. Tests now assert
against rendered tracebacks for invalid Docker JSON, create output, and
interface output; the focused strict non-live suite passed 46/46. A first
test failed only because the fake secret appeared literally on its call
line; moving fixture construction off that line made the traceback check
meaningful. No native run followed this correction.

The corrected committed blob requires a new independent source-only review.
Any native tags-only diagnostic requires separate exact one-shot
authorization. The empty-`manifests-v2` hypothesis remains untested.
Production remains HOLD.
