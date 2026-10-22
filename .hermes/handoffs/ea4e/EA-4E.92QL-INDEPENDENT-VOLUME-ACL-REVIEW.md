# EA-4E.92QL Independent Volume ACL Review

One separately approved, independent reviewer matched all seven pinned
`<commit>:<path>` blob SHA-1 values at source commit
`0d69711f7da287e44dc3008c0e4c00c49f127d76` before substantive review.
The attributable report is Codex thread
`01a16173-470f-71f3-8550-671fb34bcdeb`.

## Findings And Verdicts

1. **P2 catchable interop exception gap.** The retained handle can close
   between preflight and the `SafeFileHandle` P/Invoke marshaler's reference
   acquisition, producing `ObjectDisposedException`; loader failures such as
   `DllNotFoundException` and `EntryPointNotFoundException` also escape the
   reader (`tools/Ea4eDirectoryVolumeAclCandidate.cs:32-38`). They cannot
   produce a positive flag classification, but can interrupt a future caller
   instead of returning a defined denial. The inert fixture covers only a
   null handle, not these cases.
2. The P/Invoke declaration and pure `FILE_PERSISTENT_ACLS` classifier
   **PASS source inspection**. The documented BOOL, handle, pointer-sized
   optional outputs, DWORD sizes, output flags, and immediate last-error
   capture are represented. A failed API result denies even if its output
   bit is set. Raw flags nevertheless remain exposed after failure and must
   not become independent admission evidence.
3. Direct `SafeFileHandle` marshalling protects its lifetime during the
   P/Invoke, but preflight is not an atomic reservation. The helper does not
   establish directory type, handle provenance, desired-access suitability,
   parent topology, manifest/SID authority, effective client rights, or
   strict 92AT mapped-byte binding. The intended directory-handle and
   unsupported-transport behavior remain untested. No committed production
   caller or admission route consumes this reader.

Complete reader denial behavior: **HOLD pending source correction**.
Authenticated native issuer and production: **HOLD**. Strict 92AT: **REJECT**.
The 7/7 focused and 123/123 adjacent inert tests are not native proof;
the reviewer edited no files and invoked no native or live service.

Narrow next non-live action: define catchable-exception denial behavior,
clear failed-call flags, and use an injected inert boundary to test the
failure paths. No native retry or fallback is authorized.
