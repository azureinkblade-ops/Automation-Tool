# EA-4E.92ON source-only retained record read

Status: NON-LIVE SOURCE-ONLY / NATIVE READ NOT INVOKED.
Governing parent: `5add53882acfee4d8ae0e92180c1013ddff72e9d`.

`Ea4eAnnouncementRetainedReadCandidate` accepts only a caller-owned
`SafeFileHandle`; it opens no path. It rejects an invalid handle, directory,
reparse point, multiple links, empty record, or record over 1024 bytes. Its
native candidate would seek to offset zero, read the exact initial size plus
one EOF probe, and compare retained-handle attributes, volume/file index,
size, link count, creation time, and write time before and after. The method
returns bytes only after these checks; it does not close the caller's handle.
The intended caller must open a synchronous handle; overlapped I/O is not
supported by this candidate.

The test fixture only compiles this C# file and calls inert shape/limit
methods. It has no native-read CLI. Focused source tests passed 13/13.
No file, pipe, or receiver was opened. These tests do not qualify Win32
marshalling, filesystem race behavior, byte immutability, or issuer origin.

Before native use, a separate reviewed opener must bind the 92OM share mask
to the exact installed namespace, retain directory and record handles,
read back owner/DACL/label, reject reparse and path substitution, and compare
the creator process with an independently retained launch handle. The 92OJ
decoder and durable one-use accounting must follow before any medium client
connects. A source-only success does not close 92NK, strict 92AT, production,
or any Kilo/OpenCode receiver/model gate. Docker mutation, GPU, and ComfyUI
remain off.
