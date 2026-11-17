# EA-4E.92WW Buildx creation-owner review fix

Status: SOURCE-LEVEL REVIEW FINDINGS REPAIRED / NATIVE LAUNCHER HOLD.

One independent, read-only review of committed 92WV `701ea88` found two
actionable gaps: the same prepared attribute set could be claimed by two
creation owners, allowing a second job-handle close; and attachment accepted
an `OwnedSuspendedProcess` with invalid handles or IDs. The one-review
authorization is consumed. The reviewer ran no tests or native actions.

The factory now records one creation-owner claim on the prepared attribute
set and rejects a second claim. Attachment requires that claim to match,
the attributes to remain owned, and canonical nonzero, distinct handles and
valid process/thread IDs. Focused and adjacent injected tests passed (122).

This does not establish exclusive ownership of a caller-supplied job-handle
value if the caller builds distinct attribute sets for that same handle. The
caller must not independently close or reuse the handle while owned. The
reported process predicates are not native evidence of job membership.
Native creation-time containment, hard-deadline child termination, zero
active job members, output bounds, plugin identity through load, and local
builder/daemon identity remain unproven. No native process, Docker, Buildx,
model, GPU, receiver, handoff, or production action ran. Native and
production gates remain HOLD.
