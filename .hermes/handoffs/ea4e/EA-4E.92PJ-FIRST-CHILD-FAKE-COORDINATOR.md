# EA-4E.92PJ First-Child Fake Coordinator

The 92PJ candidate composes the 92PI value plan with a fake-port sequence:
screen the pinned parent, make at most one first-child create attempt, screen
the returned retained handle, and dispose that handle on every known return
path. It does not contain a native installation adapter or create a directory.

Focused qualification: 9 passed. Adjacent qualification: 361 passed, 3
existing skips. The first fake run exposed an incorrect test expectation for
an exception after assignment of the out handle; the corrected test asserts
that the assigned handle is disposed. A create result with no returned handle
is denied, but may have left an unobservable object. That outcome remains
HOLD for operator investigation, without path-based cleanup or retry.

No native directory creation, ACL mutation, Docker mutation, receiver/model
call, GPU generation, ComfyUI call, or production activation occurred. This
is source and fake-port evidence only. A separately reviewed native adapter,
retained-handle observation, effective-rights evidence, and a newly pinned
one-shot native authorization remain required. The strict 92AT mapped-byte
invariant remains REJECT/HOLD independently of this checkpoint.
