# EA-4E.92PT Independent Native Adapter Review

Decision: HOLD. Read-only source review by a separately delegated reviewer; no code, native operation, Docker mutation, receiver/model call, or production action was performed by the reviewer.

## Integrity gate

The reviewer queried commit `ba50d2e60e77381226e1ab48baa1ad594e94acdb` directly. All five requested Git blob SHA-1s in the Obsidian `EA-4E.92PT Independent Native Adapter Review Request.md` matched before substantive review.

## Findings

1. The one-attempt adapter is absent. `tools/Ea4eDirectory2NativeAbiCandidate.cs` declares a private import but has no caller. `tools/Ea4eDirectory2SecurityAttributesCandidate.cs` passes an unmanaged pointer only to an injected observer; `tools/Ea4eDirectory2HandleResultCandidate.cs` classifies only a returned pointer. No reviewed path/parent binding, volume and privilege preflight, one-call state machine, immediate last-error capture, exact returned-handle ownership, or uncertain-creation HOLD is wired. A non-sentinel pointer cannot be elevated to success. These requirements are in `EA-4E.92PM-NATIVE-DIRECTORY-ADAPTER-REVIEW-CONTRACT.md`.
2. `Ea4eAnnouncementFileDescriptorCandidate.ReadDirectory` can screen owner, group, DACL and label on a supplied handle, but nothing proves it is the exact creation handle or observes file type, final path, file identity, attributes/reparse state, effective rights, and no-delete-sharing behavior. A failed readback must deny without reopening by path.
3. The five-argument Unicode declaration and x86/x64 `SECURITY_ATTRIBUTES` offsets are consistent with the pinned Microsoft header and structure definition. Runtime behavior remains unproved. The public `CreateDirectory2W` documentation disagrees with its example on argument count and failure sentinel. A future caller must reject both zero and `INVALID_HANDLE_VALUE` and capture the Win32 error immediately.
4. Directory SDDL screening is structural, not an effective-access proof. The app SID is supplied by the caller; it needs independent authentication. Creation-time descriptor application, exact-handle readback, and token-specific effective rights remain unverified.

Primary references: [pinned Win32 metadata header](https://raw.githubusercontent.com/microsoft/win32metadata/76c04c2021ef4a831a6f1e06d9566002d746139b/generation/WinSDK/RecompiledIdlHeaders/um/fileapi.h), [CreateDirectory2W](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectory2w), [SECURITY_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/wtypesbase/ns-wtypesbase-security_attributes), [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo), [mandatory integrity control](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control).

## Narrowest next step

Implement a default-deny, source-only adapter candidate with explicit failure states and exact-handle observations, then obtain another independent source review. Do not call the native export, install an issuer, invoke a real receiver/model, or activate production from this report. The strict 92AT mapped-byte requirement remains REJECT/HOLD; the accepted 92DE local-container profile is a separate claim.

Local parallel requalification at this same committed source found both pinned Kilo and OpenCode executable SHA-256s still matching. A seven-module fake shared-store/text-return/recovery matrix passed 55/55 using `--confcutdir tests/hermes_core --import-mode=importlib`. An initial invocation without those pytest isolation flags failed on package/conftest import before collecting tests; it is not a product-test failure. This matrix is non-live and does not show a model response.
