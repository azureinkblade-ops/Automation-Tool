# EA-4E.92FE One-Shot Created Diagnostic Hold

Status: HOLD AT GATEWAY IDENTITY / ONE-SHOT DIAGNOSTIC CONSUMED
Governing source commit: `930e4d6cdefcf91a793ffd45e954693783f004c4`
Date: 2026-10-08 (America/Phoenix)
Run ID: `db1b8d31762a4c98bea618cafaebc252`

The read-only image/name preflight passed for the two pinned local images and
fresh run-scoped names. One bounded diagnostic then created the internal
network and two **never-started** helper containers. The 92FB created-state
gate stopped at `FakeGatewayCreatedDenied: gateway identity denied`, before
either container start, request, signal, receiver, model, or production action.

That denial bundles the returned ID shape, exact name, image identity, and
record shape. No sanitized per-field observation was retained, so the precise
subfield mismatch is **unknown**. Do not infer that it was Docker's manifest
versus config image ID merely because that is plausible. No check was relaxed
and no retry was made. The coordinator executed owned-object cleanup.
Independent read-only label- and name-filtered checks found no remaining
run-scoped containers or network.

The next non-live remediation is to separate gateway identity denials into
bounded field-specific reasons and record only sanitized identity fields while
preserving exact-ID cleanup. Requalify with fake records before requesting a
new one-shot diagnostic. The completed one-shot is consumed; it cannot be
reused. A created-state match, if later achieved, would still not qualify a
running socket peer or production execution.

`PRESTART_GATEWAY_IDENTITY_MATCH=NO`
`CONTAINERS_STARTED=0`
`REQUESTS_SENT=0`
`RELEASE_SIGNALS_SENT=0`
`LEFTOVER_RUN_SCOPED_OBJECTS=0`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`PRODUCTION_READY=NO`
