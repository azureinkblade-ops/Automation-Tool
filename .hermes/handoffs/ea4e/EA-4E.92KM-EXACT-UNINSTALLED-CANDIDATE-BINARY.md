# EA-4E.92KM exact uninstalled candidate binary

Status: NON-LIVE CANDIDATE / NOT APPROVED / NOT INSTALLED / NOT EXECUTED.
Governing committed source: `4d8b22f378ec63e0d9bb93a99d4f1bbeef8882ad`.

One versioned binary was compiled from the committed 92KB/92KI/92KJ/92KK
source using the explicit local .NET Framework compiler and references
recorded in 92KL. The build did not overwrite an existing candidate:

- Path: `output/ea4e92km-candidate-4d8b22f/preflight.exe`
- Size: 13,824 bytes
- SHA-256: `914A95979A4E066180E59BD9BBACED4E290EC024BB2B3D52D476511260CA30BB`
- Authenticode: `NotSigned`
- Git status: ignored by the existing `output/` rule; no binary staged

This path is writable worktree output, not a protected installation. The
hash is an exact local measurement, not independent operator approval. The
92KL two-build experiment already showed that rebuilding from the same
source need not reproduce these bytes; therefore a later install must use
and verify this exact candidate or separately review another exact output.
No source hash may substitute for the candidate binary hash.

The local PowerShell runtime did not support reflection-only assembly
loading, and no local `ildasm.exe` was found. Consequently, a metadata-derived
runtime-reference list was not obtained. The three managed assemblies named
on the compile command and the source-declared Windows native imports are
observed inputs, not a complete transitive runtime/import closure.

Before any protected install, an independent reviewer must approve the
exact binary SHA-256 and dependency closure, define a versioned protected
destination and store identity, and qualify the installer/ACL/reparse checks
from 92JY. A separately bounded UAC install authorization must name the
exact source and destination bytes and rollback procedure. This artifact
does not authorize Docker mutation, receiver execution, model invocation,
GPU, ComfyUI, or production activation. Production remains HOLD.
