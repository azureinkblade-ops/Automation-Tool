# EA-4E.92AP Value-Only Launch Inputs

## Scope

Non-live source candidate based on synchronized 92AO commit
`8ab986ec49940e97fc28e4372bde780b2bb238ad`. The helper re-runs
probe admission against the exact reviewed/candidate contracts and runtime,
bootstrap, and request bytes. It returns the admitted application path and
ordered argv unchanged, a sorted four-name UTF-16LE environment block
ending in two Unicode NUL characters, the exact three creation flags from
92AO, and the value-only admission evidence.

No ambient environment is inherited by this value. The Unicode block
preserves non-ASCII paths. Candidate drift and content-hash drift deny
before a value is returned. The result has no command-line string, native
buffer or process handle and grants no launch or resume authority.

## Working-Tree Evidence

- Focused launch-input tests: 9 passed; both tripwires 0.
- EA-4E.92S through 92AP bounded fake-only gate: 762 passed; both
  tripwires 0.
- Guarded Hermes Core: 4,430 passed / 35 inherited failed / 6 deselected /
  104 subtests passed. Failure identities versus committed 92AO: 0 added,
  0 missing. JUnit SHA-256:
  `727607211266427f5735f65d6d389212d4d91ea4b317825ad6dba0f974cc3734`.

Staged-export and committed-tree gates are required before qualification.
The full suite is not green; its 35 inherited failures remain open.

## Boundary

Windows command-line quoting, a mutable `CreateProcessW` command-line
buffer, a retained native environment buffer, actual flag use and the
trusted creator are separate review steps. This helper contains no DLL
binding, native process creation, resume, receiver/model invocation, GPU,
ComfyUI, or production activation. Host/runtime/profile/argv/fixture
identities and a bounded native-probe authorization remain unfrozen.
