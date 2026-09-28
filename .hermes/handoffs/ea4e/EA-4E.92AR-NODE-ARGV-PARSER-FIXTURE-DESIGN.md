# EA-4E.92AR Node argv parser fixture design

## Status and baseline

DESIGN ONLY at synchronized 92AQ commit
`302b8492f0d42319720ddcc84d257e701f3a7390`. No Node invocation,
native process call, receiver/model activity, probe, or production activation
is authorized by this document. The 35 inherited guarded-suite failures
remain open.

## Question to prove

92AQ encodes the reviewed `ProbeAdmissionContract.argv` with Windows C
runtime quoting and retains writable `CreateProcessW` buffers. Matching
Python's `list2cmdline` is not proof that the pinned Node runtime receives
the same arguments. The proof must bind the exact runtime executable and
parser behavior to the ordered eight-element contract:

1. runtime path (`argv[0]` in the Windows command line);
2. bootstrap path;
3. `--probe-id`, probe ID;
4. `--request-id`, request ID;
5. `--request`, request artifact path.

The observable Node `process.argv` should contain the runtime path, the
fixture script path in the bootstrap position, and the six following
arguments in exactly that order and spelling. Compare exact UTF-16-derived
string values, not a reconstructed command line or a lossy display string.

## Non-executing preparation

- Design a dedicated inert fixture that emits one canonical JSON record of
  `process.argv`, with a fixed schema and no imports, network, filesystem
  writes, child processes, dynamic evaluation, or application bootstrap.
  Treat fixture source bytes and output schema as separate pinned artifacts.
- Pure tests may compare 92AQ's encoder against known Windows quoting
  vectors and reject NUL, malformed Unicode, argument substitution, extra
  flags, and command-line limit drift. These tests remain fake-only and do
  not establish Node acceptance.
- Before any real fixture run, freeze the executable SHA-256, fixture SHA-256,
  host/OS identity, full argv, writable-buffer hash, explicit environment,
  current directory, process policy, time/output budgets, and expected JSON
  result. Revalidate those exact identities immediately before launch.

## Separate fixture authorization required

Running the fixture is a real process boundary, even though it is not a
receiver or model. It requires a new exact, bounded authorization. The
authorization must permit one Node fixture process only, no receiver,
model, network, GPU, ComfyUI, or production activation; specify timeout,
stdout/stderr ceilings, containment and cleanup ownership; and fail closed
on any hash, path, flag, environment, parser output, or process-count drift.
Do not reuse a historical receiver/probe authorization or treat a fake
round-trip as a substitute.

Capture raw stdout/stderr bytes, exit status, process accounting, and the
exact identity linkage as durable evidence. Reject malformed or duplicate
JSON, changed `process.argv`, unexpected stderr/side effects, timeout, or
unknown cleanup state. Never retry automatically. A successful fixture
only qualifies argv parsing for the frozen binary/fixture pair; it does
not qualify native creator setup, handle inheritance, job/AppContainer
membership, probe execution, resume, or production use.

## Next gate

Review this design and the intended inert fixture source separately. Any
fixture launch, even a single one, stops for exact authorization. Native
execution and production activation remain on hold.

## Non-live source candidate

The next source step adds `tools/ea4e92ar_argv_fixture.js`, an inert
single-record stdout writer, and `tools/ea4e92ar_parser_capture.py`, an
offline strict decoder of untrusted captured bytes. Its tests check the
exact fixture source, ordered eight-string argv, canonical one-record JSON,
Unicode/quote preservation, malformed or duplicate records, and extra or
missing arguments. Neither the fixture nor Node was executed. The decoder
does not authenticate a process or grant launch authority.

The first focused run exposed a test-harness problem: pytest used a huge
oversized-output parameter as a test ID and failed during setup. Short
explicit IDs fixed that fixture defect. The corrected focused 92AQ/92AR
gate passed 42 tests; the bounded 92S-through-92AR gate passed 804. Both
reported zero fake-only and filesystem tripwire events. Guarded working
Hermes Core reported 4,472 passed / 35 inherited failed / 6 deselected /
104 subtests passed. The 35 failure identities exactly match committed
92AQ (zero added or missing). JUnit SHA-256:
`54a973d38df913c18f9d48759002a33dbb023f146903589ff34676d6a808605b`.

Staged-export and committed-tree gates are still pending. The 35 inherited
failures remain open. No fixture run, real receiver/model, native creator,
GPU, ComfyUI, or production activation is authorized or performed.
