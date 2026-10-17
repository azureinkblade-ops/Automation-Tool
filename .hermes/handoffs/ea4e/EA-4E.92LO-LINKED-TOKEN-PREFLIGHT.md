# EA-4E.92LO linked-token preflight

Status: READ-ONLY NATIVE PREFLIGHT PASS / PRODUCTION HOLD.
Baseline: `46eea0e6cc84b17a3dc27a551ceca5d536698f45`.

The source-only candidate queries only its own process token for elevation
type and mandatory integrity SID, then reads and closes a linked token
handle if Windows supplies one. It has one accepted argument, `SELF`. It
does not request elevation, display UAC, create a process or pipe, or call
any issuer or receiver. The numeric elevation types are 1 default, 2 full,
and 3 limited.

Observed under the Codex filesystem sandbox:

```ini
CURRENT_ELEVATION_TYPE=3
CURRENT_INTEGRITY_SID=S-1-16-4096
LINKED_TOKEN=OBSERVED
LINKED_ELEVATION_TYPE=2
LINKED_INTEGRITY_SID=S-1-16-12288
```

Observed in the separately approved unsandboxed test context (not a UAC
elevation or protected issuer):

```ini
CURRENT_ELEVATION_TYPE=3
CURRENT_INTEGRITY_SID=S-1-16-8192
LINKED_TOKEN=OBSERVED
LINKED_ELEVATION_TYPE=2
LINKED_INTEGRITY_SID=S-1-16-12288
```

Thus this host exposes a linked full token to the current limited token,
while Codex sandboxing lowers the executing process from medium to low
integrity. Reading a linked token is not the same as using it to create
the protected pipe; the actual Automation Tool app process token remains
unobserved. No inference is made that the linked handle is the future
operator authority or that a pipe created under it has a compatible owner,
DACL, or mandatory label.

`python -m pytest -q -p no:cacheprovider --basetemp=output/ea4e92lo-adjacent-20261017 tests/hermes_core/test_ea4e92lo_token_pair_preflight.py tests/hermes_core/test_ea4e92ln_pipe_integrity_label.py tests/hermes_core/test_ea4e92lj_pipe_client_binding.py tests/hermes_core/test_ea4e92lg_pipe_client_process.py tests/hermes_core/test_ea4e92lf_pipe_client_token.py`

Focused result: 18 passed, 0 failed; 92LO dedicated: 2 passed, 0 failed.
The temporary compiled executable in `output/` is not a pinned production
artifact. No staged or committed-tree gate is claimed yet for this WIP.

The next bounded native step still needs exact source/binary identity,
reviewed protected pipe creation policy, actual elevated creator and
limited app process tokens, a temporary namespace, one-attempt budget,
timeout, and exact cleanup. This preflight does not authorize that step.
No Docker mutation, Kilo/OpenCode/model call, GPU/ComfyUI activity, or
production activation occurred.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_elevation_type
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_linked_token
- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
