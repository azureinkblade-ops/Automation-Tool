# EA-4E.92AQ Command-Line and Native-Buffer Contract Review

## Disposition

NON-LIVE DESIGN CANDIDATE based on synchronized 92AP commit
`6fdff6f77394d7705f20980de82e3fd2bb666170`. No source or test code
changes, native API binding, process creation, resume, receiver/model call,
or production activation are authorized by this document.

## Input Boundary

- Accept only a freshly revalidated `ProbeLaunchInputs` value from 92AP,
  its exact reviewed `ProbeAdmissionContract`, and the same still-owned
  request/profile/attribute lifecycle owner. A caller-supplied command
  line, environment pointer, flags, executable path, or working directory
  is not authoritative.
- Set non-null `lpApplicationName` to the exact admitted absolute runtime
  path. Never rely on first-token executable selection or PATH search.
- Form the command line from the entire admitted `argv`, including
  `argv[0]` equal to the application path. Quote with the Microsoft C
  runtime argument rules: quote empty or whitespace-bearing arguments;
  double backslashes immediately before a literal quote and add one
  backslash to escape that quote; double trailing backslashes before a
  closing quote. Preserve every other character and argument order.
  A separately tested pure encoder should be compared to Python's
  documented Windows `list2cmdline` behavior in tests only. Do not use a
  shell, PowerShell, `cmd.exe`, or POSIX quoting.
- Reject embedded NUL, malformed Unicode, or a command line exceeding
  32,767 UTF-16 code units including its terminating NUL. Require exact
  round-trip of admitted argv under the selected parser contract; record
  that `CommandLineToArgvW` and a program's own parser need not be identical.
  Node bootstrap acceptance must be proven with a bounded non-live
  parser fixture before any real probe.

## Buffer and Call-Argument Boundary

- Copy the command line into a writable, NUL-terminated UTF-16 buffer.
  `CreateProcessW` may modify `lpCommandLine`; never pass an immutable
  Python string/bytes object or a pointer into the frozen source value.
- Copy the 92AP UTF-16LE environment bytes into a retained native buffer.
  Its four sorted names and double Unicode NUL terminator must be checked
  against the admitted contract immediately before use. Pass non-null
  `lpEnvironment`; do not inherit the host environment.
- Hold both buffers, the non-null application-name buffer, explicit
  current-directory buffer, prepared `STARTUPINFOEXW`, attribute list,
  job/profile security owners, and their exact identity linkage in one
  lifecycle owner until the native call returns and resource ownership
  is resolved. No pointer-only transfer, early close, or caller mutation.
- Use the exact request-root path as non-null `lpCurrentDirectory`, after
  a native identity/reparse recheck. Do not inherit the host cwd or rely
  on implicit per-drive current-directory environment entries.
- Fix `bInheritHandles=FALSE`, null process/thread security-attribute
  pointers, and the exact `CREATE_SUSPENDED |
  EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT` mask
  (`0x00080404`). The prepared startup structure must retain the exact
  job/AppContainer attribute owner and have no unreviewed standard handles.
  Any flag, buffer, owner, or path drift denies before a native call.

## Required Non-Live Tests Before Implementation Qualification

- Argument cases: spaces in runtime/script/request paths, empty argument,
  literal quotes, one/multiple backslashes before quotes, trailing
  backslashes, non-ASCII and supplementary Unicode, embedded NUL, and
  UTF-16 length at and over the documented limit.
- Exact argv round-trip under the chosen parser fixture; no extra/missing
  argument, executable substitution, shell interpretation, or ambient
  environment leakage.
- Environment cases: sorted four-name block, exact double-NUL ending,
  non-ASCII paths, malformed UTF-16, extra/missing variables, changed
  values, and buffer mutation after preparation.
- Ownership cases: closed or replaced attribute owner, changed pointer,
  changed request-root identity, stale or cross-request inputs, and
  partial preparation failure. Cleanup must retain or close resources
  under the existing sticky-unknown rules; no automatic retry.
- Fake creator records argument values and pointer lifetimes but does
  not invoke any process API. Run focused, bounded, staged-only, and
  committed-tree gates; compare guarded Hermes Core failure identities
  to committed 92AP. The 35 inherited failures stay visible.

## Separation of Authority

Preparing writable buffers still does not prove their use in a native
call, create a trusted receipt, or confer resume authority. The actual
creator remains a separate, narrowly reviewed implementation and live
probe authorization. Stage 3 host/runtime/profile/argv/fixture identities
are not frozen here. `NATIVE_EXECUTION_HOLD=YES`;
`PRODUCTION_ACTIVATED=NO`.

## Primary API References

- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw
- https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-commandlinetoargvw
- https://learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments
- https://docs.python.org/3/library/subprocess.html#converting-an-argument-sequence-to-a-string-on-windows

## Non-Live Source Candidate

Following this design review, the user authorized the next source step.
The candidate adds a pure argv encoder compared against the standard
Windows quoting helper in tests, enforces the 32,767 UTF-16-unit command
line limit including NUL, and retains writable application-name,
command-line, environment and current-directory buffers with the exact
prepared startup/attribute owner. A value-only verifier rejects buffer,
startup and attribute drift. It does not bind or invoke a process API.

The first focused run had one erroneous supplementary-character boundary
expectation in the test; the production limit check denied correctly.
The corrected focused suite passed 21 tests with both tripwires at 0.
The bounded 92S-through-92AQ gate passed 783 tests with both tripwires at
0. Working-tree guarded Hermes Core: 4,451 passed / 35 inherited failed /
6 deselected / 104 subtests passed. Failure identities versus committed
92AP: 0 added, 0 missing. JUnit SHA-256:
`a7d17851eafcde6ce385da28b296974806727afd0da75ee14d74a40dfffbbc76`.

Staged-export and committed-tree gates remain required. A fake-only
buffer owner is not a trusted native creator. Node-specific parser
acceptance, native path identity/reparse checks, and any real probe remain
outside this source candidate and require separate review.
