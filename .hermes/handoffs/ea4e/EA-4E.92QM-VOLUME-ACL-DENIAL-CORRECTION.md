# EA-4E.92QM Volume ACL Denial Correction

The independent 92QL review accepted the P/Invoke declaration and pure
`FILE_PERSISTENT_ACLS` classifier, but held the reader because ordinary
interop exceptions could escape and a failed call exposed raw output flags.
This source-only correction puts the retained-handle preflight and reader
call inside a catchable-exception denial boundary. Fatal out-of-memory and
stack-overflow exceptions remain rethrown. A failed call preserves its
immediately captured Win32 error but returns zero public flags. Catchable
exceptions return `DENY:VOLUME_INFORMATION_UNAVAILABLE` with zero flags and
zero error, where zero means that no trustworthy Win32 error was captured.
An unsupported successful flag set also returns zero public flags.

The production `Read` path always supplies the native reader; an internal
injected reader permits inert fault testing and is not issuer authority.
The test fixture uses a non-owning synthetic `SafeFileHandle` and never calls
`GetVolumeInformationByHandleW`. It exercises successful and unsupported
synthetic flags, failed calls with the ACL bit set, a disposed-handle throw,
missing DLL/export throws, and a missing injected reader. Focused tests
passed 14/14; the adjacent matrix passed 130/130 before staging.

The corrected blob requires a new pinned independent review. Native
compatibility with the intended retained directory handle, parent identity,
manifest/SID provenance, effective rights, issuer admission, and strict 92AT
mapped-byte proof remain unqualified. No native volume read, directory
creation, Docker mutation, Kilo/OpenCode/model, GPU, ComfyUI, or production
action occurred.
