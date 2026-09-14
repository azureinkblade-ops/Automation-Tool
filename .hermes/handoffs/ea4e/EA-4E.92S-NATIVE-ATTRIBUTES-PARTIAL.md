# EA-4E.92S Native Attribute Adapter - Partial Implementation

Date: 2026-09-14
Synchronized baseline: ebd00dd139016944fbe27cada0bb95f094ce00f3
Status: IMPLEMENTED / FAKE TARGETED PASS / UNCOMMITTED
Native containment: NOT QUALIFIED

## Source Scope

tools/ea4e92s_windows_attributes.py: lazy explicit native attribute-list adapter;
tests/hermes_core/test_ea4e92s_windows_attributes.py: injected Windows function
tests. This evidence is the third candidate file. No process creation, native SID
validation, AppContainer profile, ACL operation or production integration added.

The adapter bounds attribute storage to 1 MiB, requires exactly two attributes,
accepts only reviewed job/security ordering, maps symbolic keys to SDK values,
and rejects added capabilities or reserved fields. Owned list wrappers retain
backing storage until deletion and reject other-owner/closed-list updates.
Attribute values remain retained by the separately tested composer. Native DLL
loading occurs only when explicitly constructing the uninjected adapter; tests
always supply fake functions and an explicit fake error reader.

Initialize size probing requires documented ERROR_INSUFFICIENT_BUFFER (122),
nonzero bounded size and initialization success. DeleteProcThreadAttributeList is
void; returning True from the wrapper means that call returned without exception,
not an independent cleanup verification or broker-crash recovery proof.

Numeric attribute identities derive from the input-bit/enum definitions in
[Microsoft WinBase.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/WinBase.h):
JOB_LIST 0x2000D, SECURITY_CAPABILITIES 0x20009.
Signatures/lifetimes checked against
[Microsoft UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/desktop/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute).
These references are design/API evidence, not pinned runtime artifact identity.

## Verification

Pinned stage2-v2 Python; existing process/network and filesystem tripwires plus
nonlive_report_host; fresh .pytest-ea4e92s-native-attributes-b.
Six test files: windows_attributes, creation_attributes, windows_job,
containment_lifecycle, parser_source and ea4e92p static inspection.
18 adapter cases + 93 predecessors = 111 passed / 0 failed, 0.32s.
Both tripwire counts zero. Initial 107-test pass predates four additional
zero-capability rejection cases and is superseded.

No actual native DLL or Windows API calls, process launch, parser/SDK/receiver/
model invocation, AppContainer/profile/ACL mutation, downloads or GPU activity.
New files not staged/committed/pushed. Full/staged/committed gates for this slice
remain unrun. Earlier ebd00dd committed full gate does not qualify this WIP.
Next source checkpoint: review and broader fake-only regression. Native SID,
process-creation binding, runtime admission, capture/timeout and actual enforcement
qualification remain OPEN. No Node or SDK launch permission is inferred.

## Adapter Review and Broader Gate

Review found that the adapter did not independently retain native attribute value
buffers. Three new fake assertions reproduced the defect before the fix. The owned
list now retains supplied values until successful deletion; update failure or
exception locks further updates while permitting cleanup. Values remain retained
on uncertain deletion. No native DLL or syscall was invoked.

21 adapter + 93 predecessor fixtures = 114 passed / 0 failed, 0.32s; both
tripwire counts zero, fresh .pytest-ea4e92s-adapter-review-green.
Full working-tree Hermes Core gate with the same pinned Python, guard/report
plugins and six predecessor OS-test exclusions: 3709 passed / 35 raw failed /
6 deselected / 104 subtests passed, exit 1, 117.34s. Exact failed-node comparison
against latest ebd00dd committed report: 35 unchanged, added 0 / resolved 0.
Process tripwire: 34 denied Popen attempts. Filesystem tripwire: 0.
Report .pytest-ea4e92s-adapter-full-a/result.xml SHA256:
504105a78ae4368d93bac5edc91bf1dc5de6d682153ecfa1e824420095584afc

Classification: working-tree no-new-regressions PASS / raw gate NOT GREEN.
Exactly the three reviewed adapter source/test/evidence files may enter bounded
staged qualification. Record final tree/export result in the vault, not by
recursively editing this evidence. No full staged/committed gate yet.
No commit/push, machine security mutation, actual native API/process/parser/SDK/
receiver/model/GPU activity. Containment remains unqualified.
