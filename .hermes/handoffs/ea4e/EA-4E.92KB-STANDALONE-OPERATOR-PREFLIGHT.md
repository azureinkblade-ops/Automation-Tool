# EA-4E.92KB standalone operator preflight candidate

Status: NON-LIVE IMPLEMENTATION / NOT INSTALLED / NOT AN ISSUER.
Governing source: `15a090a072573cd089bd365e05cc98377e3b38ec`.

The 92JY deployment contract is corrected: PowerShell is an optional
protected runtime, not a required first elevated executable. A pinned,
reviewed compiled helper may avoid dynamic script and module loading.

`tools/ea4e_docker_operator_preflight.cs` is a standalone .NET Framework
candidate that compares an expected Windows SID with the current process
token's user SID and checks `TokenElevation` using Win32 APIs. It prints a
bounded MATCH/DENY reason and exits nonzero on denial. It has no issuer,
authorization store, Docker/process-launch API, receiver, or model path.

Read-only compiler preflight on this machine:

| Field | Observation |
| --- | --- |
| Compiler | `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` |
| Version | `4.8.9221.0` |
| SHA-256 | `46809206887326D2D24DB1EFF1F3064DE972C3451ABE766B49111450A5E08E00` |
| Signature | `Valid`, Microsoft Windows |
| Owner | `NT SERVICE\TrustedInstaller` |
| Ancestors | No observed reparse points; TrustedInstaller-owned |

The candidate source SHA-256 during this checkpoint was
`3B4E4CD6B5EDBF056118DB24383963654C67BE11054BC58CC8E9DE46E37A4A28`.
One ignored worktree-output build was compiled for tests; its bytes are not
an independently approved install artifact. The compiler/runtime/dependency
closure and protected destination ACL require separate review and fresh
verification. No elevated positive path was run or inferred.

On the current unelevated host, the matching-SID input denied with
`OPERATOR_TOKEN_NOT_ELEVATED`; wrong and malformed SIDs also denied. The
focused Windows tests passed 6/6, and the adjacent fake-only suite passed
398/398 before commit. Post-commit results must be checked separately.

This implements only one precondition for a future independent issuer. The
92JU distinct durable grant store, bounded claims, protected installation,
and action-specific live authority remain open. No UAC prompt, Docker
mutation, receiver/model call, GPU, ComfyUI, or production activation
occurred. Production remains HOLD.
