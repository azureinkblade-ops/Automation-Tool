# EA-4E.92NB expected app-process identity comparison

Status: NON-LIVE READ-ONLY CANDIDATE / PRODUCTION HOLD.
Parent: `ce43896b9f325007a685455a640497612b2de5f6`.

The 92NA kernel-derived pipe-client process lease now has a separate 92NB
composition entry point that compares the observed client PID and process
creation time against an expected pair before protected-path observation.
Zero/invalid expected values and either mismatch deny. The kernel handle
remains open throughout the observation and is rechecked by 92NA afterward.

This comparison does not establish the trust of its expected pair. The pair
must come from an independently qualified, retained app-instance owner, not
from a request field, discovered PID, or the pipe client. The test fixture
uses its own inert process solely to exercise the comparison. A matching
process still reaches the existing protected-path denial on a writable file;
it does not grant authority.

Changed files:

- `tools/Ea4ePipeClientPathObservationCandidate.cs`
- `tests/hermes_core/fixtures/ea4e92mz_pipe_client_path_probe.cs`
- `tests/hermes_core/test_ea4e92mz_pipe_client_path_observation.py`
- this evidence file

Focused native gate: 15 passed, 0 failed. Adjacent current-tree gate across
92NA, 92MZ, 92KY, 92LC, 92LD, 92LA, 92LF, 92LG, 92LJ, 92LN, 92MO, 92MP,
92MR, 92MS, 92MV, and 92MW: 143 passed, 3 permission-based skips, 0 failed.
Native pipe tests used the permitted test environment; the filesystem sandbox
blocks local pipe connection before these observations.

Still open: independently trusted app-instance launch/package receipt,
protected pipe/server policy, same-account operator separation, complete
installed issuer and runtime closure, and bounded live authorization. Strict
92AT mapped-byte proof remains REJECT/HOLD; accepted 92DE local-container
provenance is a separate, weaker contract. No Docker mutation, receiver,
model, GPU/ComfyUI, or production activation occurred.
