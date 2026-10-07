# EA-4E.92EL Prestart Diagnostic Qualification

Status: fake-only qualified; diagnostic run pending.

The operator approved one diagnostic-only run against image
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.
It may create one fresh internal network and two never-started temporary
containers, inspect the exact returned IDs, report the prestart field mismatch,
and remove only those IDs. It may not start or signal a container, send a marker
request, invoke Kilo/OpenCode/a model, or activate production.

`inert_peer_prestart_diagnostic.py` has no start or signal call. It uses the
already-qualified Docker driver only for image/name preflight, create, inspect,
and exact-ID cleanup. It emits attachment names, observed endpoint network IDs,
and match booleans, but not arbitrary inspect records. If cleanup fails, it
reports HOLD and the still-owned IDs for operator inspection.

Focused fake-only qualification: 94 passed, 0 failed, including three new
diagnostic tests and the existing preflight/created/coordinator/driver ladder.
No Docker command was invoked by these tests. A diagnostic match or mismatch
cannot authorize a subsequent container start. The 92AT exact mapped-byte
requirement remains REJECT; production remains HOLD.
