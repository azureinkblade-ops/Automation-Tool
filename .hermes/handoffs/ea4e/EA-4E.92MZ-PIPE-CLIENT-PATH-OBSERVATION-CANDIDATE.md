# EA-4E.92MZ pipe-client path observation candidate

Status: NON-LIVE CANDIDATE / NOT AN ISSUER / PRODUCTION HOLD.
Parent: `392d7fdbf1c3df611217d6043b0fdf78dd12e1b2`.
Profile: accepted 92DE local-container profile only. Strict 92AT remains
REJECT/HOLD on exact mapped-image-byte proof.

This slice composes the existing read-only pipe process/token observers with
the handle-based protected-path access check. The token observer now permits
an internal callback while the validated client impersonation token remains
open and the issuer thread is impersonating; its `finally` still reverts or
fails fast. The current-process path probe remains available and unchanged in
behavior. A new path entry validates the bound token SID and unelevated state
before using it for owner/effective-rights and optional byte-snapshot checks.
The composition checks the retained client process before and after the
observation, and returns only a denial or read-only match.

Changed files:

- `tools/Ea4ePipeClientTokenCandidate.cs`
- `tools/Ea4eProtectedPathAccessCandidate.cs`
- `tools/Ea4ePipeClientPathObservationCandidate.cs`
- `tests/hermes_core/fixtures/ea4e92mz_pipe_client_path_probe.cs`
- `tests/hermes_core/test_ea4e92mz_pipe_client_path_observation.py`
- this evidence file

The native negative fixture uses a self-process pipe client and an inert file.
It proves wrong SID, wrong retained process, malformed hash, writable target,
and missing target deny. The writable target reaches `APP_OWNS_OBJECT`; the
missing target reaches `OPEN_DENIED`. The fixture does not supply a trusted
launcher-owned app receipt or protected pipe.

Exact staged tree before adding this evidence:
`1dd90b6e54b6dd62a7731bea807426cf87e21b72`.
An isolated archive of that staged tree passed:

- 92MZ, 92KY, 92LC, 92LD, 92LA, 92LF, 92LG, 92LJ, 92LN native pipe/path
  tests: 54 passed, 3 permission-based skips, 0 failed. These were run in
  the permitted native environment because this host's filesystem sandbox
  blocks the named-pipe fixtures before their observations.
- 92MO, 92MP, 92MR, 92MS, 92MV, 92MW adjacent issuer-candidate tests:
  79 passed, 0 failed.

The combined 15-file gate was repeated against final staged tree
`b25572d8e74ef2878400b200546485b87be1f17d`: 133 passed, 3 skipped,
0 failed. This last evidence-text update does not change source or tests.

This is not an authority API. An arbitrary caller could provide the expected
process handle, SID, path, or token to these internal candidates; the fixture
does so. No protected launcher receipt, installed pipe ACL/integrity label,
independently approved policy or binary, complete runtime dependency closure,
UAC install, current store/authority binding, Docker action, or receiver/model
call is established. A positive read-only observation must not be promoted to
an issuance or production-activation decision. No GPU/ComfyUI activity or
production activation occurred.
