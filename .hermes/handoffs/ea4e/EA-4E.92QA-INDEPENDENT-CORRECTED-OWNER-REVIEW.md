# EA-4E.92QA Independent Corrected Owner Review

One separately approved, independent read-only reviewer queried all eight
requested Git blobs directly at source commit
`a04213b66f8af2040518119e5dc8daafa73c1a9e` and reported exact matches:

| Blob | Observed SHA-1 |
| --- | --- |
| `tools/Ea4eDirectory2OneAttemptCandidate.cs` | `c616d175662a1cf5a9acd057ac47b2cb04216444` |
| `tools/Ea4eDirectory2NativeAbiCandidate.cs` | `4baae92bcd482fa33730e0a68af50a20ca3d9d8c` |
| `tools/Ea4eDirectory2SecurityAttributesCandidate.cs` | `0c56d8a1d1ea2a92b5d74618140b598c7ddafe08` |
| `tools/Ea4eDirectory2RetainedShapeCandidate.cs` | `75be320f095c53bbd8ce5b5f046c9f6d09b047ca` |
| `tools/Ea4eDirectoryInstallPlanCandidate.cs` | `fe214ce153d45aed9f5500b4afe510ddb522821b` |
| `tools/Ea4eAnnouncementNamespacePathCandidate.cs` | `5f3226d030e16aeb939f52d27fec4b97bcbaf3ba` |
| `tools/Ea4eAnnouncementFileDescriptorCandidate.cs` | `c55ce002475766e628f104a0fac00f63b05b3a93` |
| `tests/hermes_core/test_ea4e92pw_one_attempt_source.py` | `486f2bb73988b65cfec27e5e38af089f2808d710` |

## Findings

1. **Medium - failed-close uncertainty collapses into generic denial.** If
   `CloseHandle(raw)` fails at owner line 78, the thrown error is caught and
   reported as `DENY:ATTEMPT_UNCERTAIN` at line 104. The output `lastError`
   remains zero. One close attempt is made, but the source cannot claim the
   handle was closed or clearly signal possible created-object reconciliation.
2. **High - issuer provenance/effective rights unproved.** The owner screens
   caller-supplied parent, manifest, SID, path, and SDDL values without
   authenticating their origins, the ACL-capable volume, privilege, or first-
   child absence. Descriptor readback is structural and does not attest
   client-token effective rights (owner line 15; descriptor reader line 189).

The reviewer found that the 92PY post-return/pre-wrapper gap is corrected in
source: a non-sentinel raw handle is transferred to the exact `SafeFileHandle`
or receives one close attempt, including on catchable exceptional exits. It
found no source-level double-close or false-success path. One native call per
invocation, immediate internal last-error capture, both sentinel checks, and
same-wrapper shape/descriptor readback remain present. Fatal runtime behavior
and successful native closure were not tested.

Source-only owner **HOLD**. Native issuer **HOLD**. Live receiver/production
readiness **REJECT as a claim**. Strict 92AT mapped-byte proof remains REJECT.
Narrowest next non-live action: distinguish failed-close/post-call uncertainty
and preserve captured last-error, then review the newly pinned source. The
reviewer changed no files and performed no native, Docker, receiver/model,
GPU, ComfyUI, or production action.
