# EA-4E.92SV interface failure state candidate

Date: 2026-10-26

The 92SU tags-only native run passed post-start containment, then Docker
rejected the loopback-interface exec before any server request. The cause
could not be classified after exact-owned cleanup. This source-only
successor makes one bounded read-only inspect if that interface exec fails,
rechecks the complete effective-container envelope and exact ownership,
and reports either the existing bounded stopped-process exit metadata or a
fixed interface-inspection denial. It does not emit Docker stderr or logs,
weaken the containment predicates, send `/api/tags` after failure, or retry.

Focused strict non-live tests passed 55/55, including a fake process exit
between start and exec and a fake rejected exec while still running. Both
paths clean up exactly the owned fake container and send no server request.
No Docker, Ollama, model, GPU, receiver, or handoff ran for this change.
Fake tests do not establish native behavior.

The committed candidate needs an independent source-only review and fresh
exact one-shot native authorization before any tags-only diagnostic. The
empty-`manifests-v2` hypothesis remains untested. Production remains HOLD.
