# EA-4E.92AV Fake-Only Creator Owner

## Scope and authority

NON-LIVE SOURCE CANDIDATE on synchronized 92AU commit
`69140ab3e23ab8b92d4a42c0ef191ce70e33fba3`. This slice models the
one-attempt creator ordering specified by 92AT and the fake-only lane left
open by 92AU. It does not bind a native API, inspect host paths, start a
process, execute the Node fixture, resume a thread, or invoke a receiver,
model, GPU, ComfyUI, or production activation.

## Source boundary

`tools/ea4e92av_fake_creator_owner.py` accepts only the exact 92AS
`CreationCallPlan` object. `begin_fake_call` rechecks the plan through the
injected inspector and consumes one simulated attempt before a return can
be recorded. A canonical result is retained as `returned_untrusted`; even
all-true caller-supplied creation predicates cannot produce a verified
state or resume authority. Malformed/ambiguous returns are retained for
fake reconciliation and make the owner sticky `unknown`. Every later
transition rechecks the same plan and owner. Replay, changed path/buffer
owner, cross-request plan, cancellation during the attempt, cleanup
ambiguity, or concurrent duplicate attempt denies further progress.

`closed_fake` records only a caller-supplied fake cleanup result. It is not
OS cleanup evidence and must never be accepted by the native creator or
pre-resume verifier. No callback, subprocess operation, Windows binding,
or positive native receipt exists in this module.

## Verification

Focused fake-only tests: 14/14 passed. Bounded 92S-through-92AV:
834/834 passed, with both filesystem and fake-only tripwires at zero.
Guarded working Hermes Core: 4,502 passed / 35 inherited failed /
6 deselected / 104 subtests passed. Failure identities versus committed
92AS: 0 added, 0 missing. Final working JUnit SHA-256:
`247681d8d5850d46acda9b9400c84ab286e2fa7f8bbc0510ffbb6f3d948fad77`.
The broad suite remains non-green; its fake-only guard blocked 32 inherited
subprocess attempts. Staged-export and committed-tree qualification are
still required before the source checkpoint can be accepted.

## Exit state

`FAKE_CREATOR_OWNER_SOURCE_READY_FOR_STAGED_REVIEW=YES`

`NATIVE_IMAGE_BINDING_QUALIFIED=NO`

`TRUSTED_CREATOR_IMPLEMENTED=NO`

`NATIVE_PROCESSES_STARTED=0`

`PRODUCTION_ACTIVATED=NO`
