# EA-4E.92IZ Kilo container observation checkpoint

Status: qualified non-live observation contract only. Production remains HOLD.

Governing predecessor: `674ed1b10a7641df576f2217defc9c8b33bbc6b6`.
This checkpoint adds a separate SQLite store for caller-reported Kilo container
start and terminal facts. It does not start, inspect, signal, or remove Docker
objects. It does not invoke Kilo, OpenCode, a provider, or a model.

The start row binds one attempt to the existing created-container report, the
receiver start fence, exact container and network IDs, and an owner label. It
rechecks the claim, delegation, lease, and lease window in the write transaction.
Duplicate starts deny. The terminal row retains bounded stdout/stderr bytes,
their digests, exit code, and the start digest. Identical terminal replay is
idempotent; divergent replay denies. A terminal report can be retained after
later cancellation so recovery does not erase an observed outcome.

Verification with the stage-2 Python environment and a unique writable pytest
temp root:

- Focused new + adjacent claim/created-report/host-owner tests: 48 passed.
- All `test_ea4e92i*.py` plus delegated claim owner and text process
  observation/owner tests: 127 passed.
- The first broader test command did not collect because PowerShell did not
  expand the file glob for pytest. The rerun passed 127/127.
- The first focused failure was test-fixture-only: a cancellation assertion
  expected a later rejection than the witness loader's fail-closed rejection,
  and a concurrent writer reused a thread-bound SQLite connection. Each
  writer now opens its own stores; the corrected ladder passed.

This store accepts reports from its caller. It does not attest daemon process
identity, socket ownership, image-section bytes, or stdout origin. It is not a
container launch permit or a production receiver owner. The fake gateway
delivery qualified in 92IY and the original 92AT mapped-byte hold are unchanged.
Real Kilo/OpenCode receiver and model activity remain unauthorized.
