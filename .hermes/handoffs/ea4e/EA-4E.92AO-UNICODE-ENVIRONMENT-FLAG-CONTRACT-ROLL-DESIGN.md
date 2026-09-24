# EA-4E.92AO Unicode Environment Flag Contract Roll Design

## Disposition

NON-LIVE DESIGN ONLY. Governing source baseline:
`2dd886b600eba398769f3e7ea8888eea118e201d`. This checkpoint does not
change the creation receipt validator, construct launch inputs, bind a native
API, create a process, or grant resume authority.

## Conflict

EA-4E.92S freezes an explicit, sorted environment of SystemRoot, TEMP, TMP,
and WINDIR for each probe. The next value-only launch-input builder should
serialize that environment as Unicode, preserving non-ASCII Windows paths.
Microsoft documents that a Unicode `lpEnvironment` block supplied to
`CreateProcessW` requires `CREATE_UNICODE_ENVIRONMENT` (`0x00000400`).
The current EA-4E.92AE receipt accepts exactly `CREATE_SUSPENDED |
EXTENDED_STARTUPINFO_PRESENT` (`0x00080004`) and denies extra flags.
Consequently, a correct explicit Unicode environment would be denied by
the frozen receipt contract. Omitting the flag or silently switching to ANSI
is not an acceptable workaround.

## Proposed Narrow Roll

1. Keep the explicit four-name environment and its admission validation.
   Serialize it as a sorted, double-NUL-terminated Unicode block retained
   by the future creation owner. Do not inherit the ambient environment.
2. Change the receipt's exact required flags to `CREATE_SUSPENDED |
   EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT` (`0x00080404`).
   All other bits, including flags supplied by a caller, remain denied.
3. Update only the EA-4E.92AE and 92AF receipt/observation fixtures and
   affected contract text. Prove the prior two-flag value is denied, the
   exact three-flag value is accepted as an *untrusted value*, and any
   additional bit or malformed type is denied before observation.
4. Build value-only launch inputs from the exact admitted `argv` and
   environment, with a separately specified Windows argument-quoting
   contract. Retain writable command-line and environment buffers with the
   creation owner. No native call follows from this design.
5. Inspect any sealed hash/identity references before implementation;
   rebind only genuinely affected artifacts. Run focused, bounded,
   staged-only, and committed-tree fake-only gates, comparing the guarded
   Hermes Core failure identities to this baseline. The inherited failures
   must remain visible.

## Boundary

The flag roll is a source-contract prerequisite, not native qualification.
There is still no trusted creator, positive resume authority, frozen
host/runtime/profile/argv/fixture for a real probe, receiver execution, or
production activation. A separately bounded authorization is required for
any native process creation.

## Primary References

- https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw

## Implementation Result

The narrow non-live roll adds the Unicode flag to the receipt's exact
required mask and updates only the EA-4E.92AE/92AF fixtures. The prior
two-flag value, each missing required bit, extra bits, and malformed types
deny. An exact three-flag receipt remains an untrusted in-memory value;
this change does not prove the flag was used in a native call or that a
Unicode environment block was supplied.

- Focused receipt/observation: 46 passed; tripwires 0/0.
- Bounded EA-4E.92S through 92AO: 753 passed; tripwires 0/0.
- Working-tree guarded Hermes Core: 4,421 passed, 35 inherited failed,
  6 deselected, 104 subtests passed. Failure identities versus committed
  92AN: 0 added, 0 missing. JUnit SHA-256:
  `791a60a1c649c22a1782354f826b4f6be252641350c28016f07d0189a56b9495`.
- The first full-run report path was outside the test root and the
  filesystem guard denied report creation. The corrected run wrote its
  report inside the test root; this was a test-command error, not a
  production-code failure.

Staged-export and committed-tree verification are still required before
this implementation is called qualified. The value-only launch-input
builder in item 4 above remains future work.
