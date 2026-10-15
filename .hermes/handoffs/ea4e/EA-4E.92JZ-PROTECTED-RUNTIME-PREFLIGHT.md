# EA-4E.92JZ protected runtime preflight

Status: NON-LIVE READ-ONLY OBSERVATION / PARTIAL.
Governing source: `36b34d1e4692b199cc012d96a3be1396a148ea7d`.

On 2026-10-14, the proposed Windows PowerShell runtime at
`C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` was inspected
without launching it or prompting for elevation:

| Field | Observation |
| --- | --- |
| File version | `10.0.26100.8972` |
| Length | `495616` bytes |
| SHA-256 | `60C9B29843624DD8AF6B6A7B26147753BE6AEEF65098B9A503CC50850AFE410F` |
| Authenticode | `Valid`, signer `Microsoft Windows` |
| Owner | `NT SERVICE\TrustedInstaller` |
| File DACL | Users/read-execute; TrustedInstaller/full control |

The inspected ancestors `C:\Windows`, `C:\Windows\System32`,
`C:\Windows\System32\WindowsPowerShell`, and the `v1.0` directory were
not reparse points. Their owners were TrustedInstaller or SYSTEM. The
candidate protected base `C:\Program Files` was also not a reparse point
and was TrustedInstaller-owned. These are path-based observations, not a
handle-bound effective-access or race-proof installation attestation.

PowerShell is one candidate runtime, not the mandated issuer. A protected,
reviewed compiled helper may be preferable if it avoids dynamic script or
module loading. This check does **not** qualify a helper, script, Python
interpreter, module closure, store, installer, or UAC ceremony. If selected,
PowerShell must run with explicit `-NoProfile -NonInteractive` semantics and
must not load user-controlled profiles, modules, or scripts. The executable
hash, signer, resolved path, complete ancestor chain, and effective ACL must
be checked again at the separately authorized installation/issuance time.
Windows updates may legitimately change the hash.

The next non-live implementation remains a reviewed, self-contained helper
closure and fake-only source/ACL/store tests under 92JY. No elevation,
installation, Docker mutation, receiver/model call, or production activation
occurred. Production remains HOLD.
