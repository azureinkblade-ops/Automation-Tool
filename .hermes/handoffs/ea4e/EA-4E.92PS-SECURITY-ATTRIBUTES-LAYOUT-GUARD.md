# EA-4E.92PS Security Attributes Layout Guard

Status: SOURCE-ONLY LAYOUT PASS / NATIVE CREATE HOLD. Parent:
`42240934bdd3f06394f20418439332ffaa553fb8`.

The 92PR inert observer used the same managed structure type as the producer.
This checkpoint adds an explicit layout check before the observer is called.
It requires a DWORD at offset zero, the descriptor pointer at offset four
on a 32-bit process or eight on a 64-bit process, a four-byte inherit BOOL at
offset eight or sixteen respectively, and total structure size twelve or
twenty-four bytes. The fixture prints the runtime pointer width, offsets,
size, and guard result without calling a native directory API.

The first test run failed because the new guard incorrectly calculated the
64-bit structure size as twenty bytes and ignored trailing alignment. The
observed x64 layout was `8:0:8:16:24`; the guard was corrected to the explicit
24/12-byte sizes. Adjacent source tests then passed 62/62, and all 50
`Ea4e*.cs` candidate sources compiled as an ignored diagnostic library.
Staged-byte and post-commit results are recorded in the Obsidian continuation.

This does not independently validate the native `CreateDirectory2W` return,
the supplied descriptor's treatment by Windows, parent-path identity, ACL
effective rights, retained-handle readback, or cleanup. No directory, issuer,
receiver, model, GPU, ComfyUI, or production action occurred. Independent
ABI/security review and a separately bounded native qualification remain
mandatory; strict 92AT stays REJECT/HOLD.
