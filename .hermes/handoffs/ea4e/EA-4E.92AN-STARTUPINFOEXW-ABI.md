# EA-4E.92AN STARTUPINFOEXW ABI

## Scope

Non-live, value-only ABI preparation after the synchronized EA-4E.92AM
checkpoint `caeca77abd8419474c99bfd1139fb9b56a95e05a`. This slice defines
the 64-bit `STARTUPINFOW`/`STARTUPINFOEXW` layout and builds a structure
whose `cb` is `sizeof(STARTUPINFOEXW)` and whose attribute pointer addresses
the exact open `NativeAttributeList` buffer. It retains the complete
`PreparedAttributes` owner, not only a raw pointer. Closed, incomplete or
cross-owner attribute lists deny before a value is returned.

The helper contains no DLL binding, process call, resume operation, command
line, environment, receiver or model invocation. A prepared structure is
**not** proof of process creation or containment and grants no authority.
Its caller must still retain the attribute owner through a future separately
reviewed native call. No such call exists in this slice.

## Working-tree verification

- Focused ABI, attribute-handoff and Windows-attribute tests: 39 passed.
- Fake-only EA-4E.92S-through-92AN bounded gate: 748 passed, zero
  process/network and filesystem tripwire events.
- Full guarded Hermes Core: 4,416 passed / 35 failed / 6 deselected /
  104 subtests passed. Compared with committed 92AM, 0 added and 0 removed
  failure identities. JUnit SHA-256:
  `d0848696fe3a44403f1bde51a0bc606b11ef31b470c66f4e94c599a85727787e`.
  The full suite is not green; its 35 inherited failures remain open.

## Primary ABI references

- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-startupinfow
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-startupinfoexw
- https://learn.microsoft.com/en-us/windows/win32/procthread/creating-processes

## Boundary

`NATIVE_CREATOR_IMPLEMENTED=NO`; `NATIVE_EXECUTION_HOLD=YES`;
`POSITIVE_RESUME_AUTHORITY=NO`; `RECEIVER_QUALIFIED=NO`;
`PRODUCTION_ACTIVATED=NO`. Host/runtime/profile/argv/fixture identities and
any native-probe authorization remain separate and unfrozen.
