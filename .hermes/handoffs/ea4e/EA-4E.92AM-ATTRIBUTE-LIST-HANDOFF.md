# EA-4E.92AM Attribute-List Handoff

## Scope

Non-live compatibility step after EA-4E.92AL. The suspended-process helper
previously required an integer attribute handle, while the reviewed Windows
attribute adapter retains a `NativeAttributeList` with its owned buffer.
The helper now accepts that exact owned, complete list and passes its retained
buffer to an injected creator. The legacy integer fake path remains unchanged.

Before the injected creator is called, the handoff rejects closed/failed
lists, incomplete keys, missing or substituted buffers/values, a different
attribute API owner, invalid job/SID pointers, and retained-buffer drift.
The test path uses an injected fake kernel and fake process API. No native
process creator, `CreateProcessW`, resume, receiver or model call was added.
The caller-constructed 92AE receipt and 92AF observation remain untrusted;
this is not a positive resume-verdict implementation.

## Working-tree verification

Base: `f08fc135187dfad33dbabb35443f5c850cb0482a`.

- Focused new handoff, suspended-process and Windows-attribute tests:
  71 passed.
- Fake-only EA-4E.92S-through-92AM bounded gate: 740 passed, zero
  process/network tripwire events, zero filesystem tripwire events.
- Full guarded Hermes Core: 4,408 passed, 35 failed, 6 deselected,
  104 subtests passed. Compared with committed 92AL, added failure identities
  0, removed 0. JUnit SHA-256:
  `17603da38011c8392f324fd60abf5a05431e8982c318a887de073c1cbe975a87`.
  The 35 inherited failures remain visible; this is not a green full gate.

## Boundary

`NATIVE_CREATOR_IMPLEMENTED=NO`; `NATIVE_EXECUTION_HOLD=YES`;
`POSITIVE_RESUME_AUTHORITY=NO`; `RECEIVER_QUALIFIED=NO`;
`PRODUCTION_ACTIVATED=NO`. The exact host/runtime/profile/argv/fixture and
native-probe authorization remain separate and unfrozen.
