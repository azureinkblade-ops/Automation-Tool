# EA-4E.92PD ProgramData known-folder lookup

Status: READ-ONLY LOOKUP CANDIDATE / INSTALLATION HOLD.
Governing parent: `7a1fb7f711a83a3e82ef712b4d6e9105e884d902`.
Profile: accepted 92DE trusted local-container host only.

The C# candidate calls `SHGetKnownFolderPath` for `FOLDERID_ProgramData`
with default flags and a null token, copies the returned Unicode path, and
releases its COM-allocated memory. The local read-only fixture returned the
existing ProgramData directory. The test compared the returned value with
this host's `PROGRAMDATA` environment value only as a diagnostic cross-check;
the environment value is not an authority input for the installer or 92PC.

Focused tests passed 2/2. Adjacent precommit tests passed 334 with 3 existing
symlink skips. The source has no directory creation, file open, installer,
pipe, Docker or receiver route. A known-folder string does not attest that
any descendant is installed, protected, non-reparse, or controlled by a
trusted creator. The 92PB observation that the planned Hermes namespace is
absent remains the operative installation HOLD.

Before any native installation, a separately reviewed, pinned installer
must define exact component creation, retained-handle topology and descriptor
readback, collision behavior, audit, cleanup and effective medium-token
denials. No previous readback-only one-shot approval authorizes installation.
Full 92NK, receiver/model, and production remain HOLD.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath
- https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid
