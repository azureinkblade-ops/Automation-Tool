# EA-4E.92QC Independent Owner Close Review

One separately approved independent reviewer inspected committed source only at
`bd198514f2e06e518f9261ffa9f74fc8d687ea27`. All eight pinned Git blobs
matched the request:

| Blob | Observed SHA-1 |
| --- | --- |
| `tools/Ea4eDirectory2OneAttemptCandidate.cs` | `d7fa102b7ea580ea9189070e90d10fbf0f2fdbdc` |
| `tools/Ea4eDirectory2NativeAbiCandidate.cs` | `4baae92bcd482fa33730e0a68af50a20ca3d9d8c` |
| `tools/Ea4eDirectory2SecurityAttributesCandidate.cs` | `0c56d8a1d1ea2a92b5d74618140b598c7ddafe08` |
| `tools/Ea4eDirectory2RetainedShapeCandidate.cs` | `75be320f095c53bbd8ce5b5f046c9f6d09b047ca` |
| `tools/Ea4eDirectoryInstallPlanCandidate.cs` | `fe214ce153d45aed9f5500b4afe510ddb522821b` |
| `tools/Ea4eAnnouncementNamespacePathCandidate.cs` | `5f3226d030e16aeb939f52d27fec4b97bcbaf3ba` |
| `tools/Ea4eAnnouncementFileDescriptorCandidate.cs` | `c55ce002475766e628f104a0fac00f63b05b3a93` |
| `tests/hermes_core/test_ea4e92pw_one_attempt_source.py` | `887d92f04ef144eabec1e1a2c0f1772183a93cc8` |

## Findings

1. **Medium - wrapper-close failure is unclassified.** After transfer to
   `SafeFileHandle`, a shape or descriptor denial reaches `owned.Dispose()`
   in the outer `finally` of `Ea4eDirectory2OneAttemptCandidate.cs`.
   `Dispose()` does not report whether the underlying native close succeeded.
   The distinct `DENY:RAW_HANDLE_CLOSE_UNCERTAIN` status covers only the
   pre-wrapper raw handle. A failed wrapper close can therefore be reported
   as an ordinary readback denial, without identifying possible handle and
   created-object reconciliation work. The reviewer found no false success
   or retry in the pinned source.
2. **High - issuer prerequisites and effective rights are unproved.** The
   caller-supplied parent, manifest root, and SID are not authenticated here;
   ACL-capable volume, privilege, first-child absence, and client-token
   effective rights remain unverified.

The reviewer accepted the source-level distinction for a failed raw close,
the copied native error, dual-sentinel screening, one native invocation per
method, and same-wrapper shape/descriptor readback. This was not a native
runtime test. Source-only owner **HOLD**; native issuer **HOLD**; live
receiver/production readiness **REJECT as a claim**. The strict 92AT
mapped-byte invariant remains **REJECT**.

The narrow next non-live action is an independently reviewed post-transfer
ownership/close design that reports unobserved or failed closure distinctly,
without risking a second close of a recycled raw handle. `SafeHandle` raw
access and invalidation require care: Microsoft's `DangerousGetHandle` and
`SetHandleAsInvalid` documentation does not make a failed close into proven
cleanup. No raw-close workaround, native call, Docker mutation, receiver or
model call, GPU/ComfyUI action, or production activation occurred in this
review.

## Follow-on design constraint

This is maintainer analysis, not part of the independent review verdict.
`SafeFileHandle` is sealed in the local .NET Framework runtime, while the
existing shape and descriptor readers accept `SafeFileHandle`. A custom
observable `SafeHandle` would require a reviewed reader/interface change, not
just a replacement at the owner. Any explicit raw `CloseHandle` design must
pin lifetime, prevent a second close after success, and preserve an honest
uncertain status after failure. Calling `SetHandleAsInvalid` on a failed close
would suppress cleanup without proving the resource was released. Merely
renaming a denied readback to a close-success status is also not a proof.
No implementation of this design is authorized by the 92QC review result.

Primary API references:
[DangerousGetHandle](https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.safehandle.dangerousgethandle),
[SetHandleAsInvalid](https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.safehandle.sethandleasinvalid),
[ReleaseHandle](https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.safehandle.releasehandle),
[releaseHandleFailed MDA](https://learn.microsoft.com/en-us/dotnet/framework/debug-trace-profile/releasehandlefailed-mda).
