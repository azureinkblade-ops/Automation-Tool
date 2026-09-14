# EA-4E.92S Creation Attribute Composition - Partial Implementation

Date: 2026-09-14
Baseline: 2b37424378a8c78f57d5c99ddafc84af2b0cb4e2
Status: FAKE TARGETED PASS / UNCOMMITTED / NATIVE NOT QUALIFIED

## Scope

tools/ea4e92s_creation_attributes.py and
tests/hermes_core/test_ea4e92s_creation_attributes.py, plus this evidence.
No native attribute adapter, process launcher or security profile implemented.
The injected API uses symbolic JOB_LIST and SECURITY_CAPABILITIES keys; native
attribute numbers and syscall signatures remain separately reviewed work.

Composition retains a single prepared job handle and zero-capability AppContainer
descriptor. Capability pointer/count and Reserved are zero; SID pointer is supplied
by the trusted caller along with its storage owner. Pointer bounds checks do not
validate SID contents, profile identity, filesystem policy or actual job ownership.
No arbitrary capabilities or launch-authority artifact are accepted or returned.

Buffers remain referenced until attribute destruction succeeds. Cleanup uncertainty
preserves the owned wrapper on UnknownAttributeCleanup.prepared and blocks repeated
close until caller reconciliation. The caller must retain that evidence/wrapper;
this is not a durable store or cross-process ownership recovery implementation.

Referenced attribute values must persist until list destruction, per
[Microsoft UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/desktop/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute).
Structure fields checked against
[Microsoft SECURITY_CAPABILITIES](https://learn.microsoft.com/en-us/windows/win32/api/Winnt/ns-winnt-security_capabilities).
No creation-time assignment, actual AppContainer or network denial is proven here.

## Verification

Pinned stage2-v2 Python; existing fake_only_guard, filesystem_guard and
nonlive_report_host plugins; fresh basetemp .pytest-ea4e92s-attributes-b.
Five targeted test files: creation_attributes, windows_job, containment_lifecycle,
parser_source and ea4e92p_static_binary_inspection.
24 composition fixtures + prior 69 = 93 passed / 0 failed / 0.26s.
Process/network tripwire events 0; filesystem tripwire events 0.
Initial 23 composition fixtures passed before adding the partial-cleanup buffer-
lifetime correction/regression test. No safety assertion weakened.

Native WinDLL/job/attribute/process/profile/ACL calls: none. Parser/SDK/receiver/
model/GPU/ComfyUI execution: none. Staging/commit/push/deletion: none.
Full/staged/committed regression for the new Windows/attribute slice remains unrun;
earlier committed full gate cannot qualify these uncommitted files.
Six uncommitted candidates now comprise the resource and composition slices.
Next: review/qualify their combined source checkpoint before native adapter/probes.

## Combined Source Review Follow-Up

The combined review fixed the adjacent job helper's missing owned-handle context
on uncertain cleanup; the composition helper itself was unchanged. Four enhanced
job assertions reproduced the issue, then the five-file bounded suite passed
93/0 with zero tripwire events.

Full working-tree gate now completed: 3688 passed / 35 unchanged raw failed /
6 unchanged OS deselections / 104 subtests passed, exit 1, 117.29s. Exact failed
identities match committed 2b374243 evidence; added 0 / resolved 0. Process
tripwire events 34 denied Popen attempts; filesystem 0. Not full green.
Report .pytest-ea4e92s-native-full-a/result.xml SHA256:
9fad2e803dd62ae673db47a2412b2cfbb87f6a75e1b1081a5ceec220e4bd61a6

Proceed only with the six-file reviewed staged checkpoint, not native launch.
Record final staged tree/export result in the vault. No commit/push, native
attribute/profile/ACL call, parser/SDK execution or isolation proof claimed.
