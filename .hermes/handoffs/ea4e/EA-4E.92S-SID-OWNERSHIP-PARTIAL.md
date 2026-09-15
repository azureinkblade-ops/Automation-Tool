# EA-4E.92S SID Ownership - Partial Implementation

Date: 2026-09-14
Governing source baseline: 00ff4eff3221c3ec716ff3856549ed12aaabbc21
Status: IMPLEMENTED / BOUNDED FAKE-ONLY PASS / UNCOMMITTED
Native containment: NOT QUALIFIED

## Scope and Contract

Three candidate files: tools/ea4e92s_sid_ownership.py,
tests/hermes_core/test_ea4e92s_sid_ownership.py and this evidence.
Existing source modules remain unchanged. The helper has no native DLL loader;
all SID operations are injected. No profile is created or inspected.

The caller supplies a reviewed profile name and independently pinned immutable
SID bytes. The injected API derives a newly owned pointer, validates it before
length/read, and supplies an exact byte snapshot. Validation must return exact
True; byte identity and length must match before attribute composition. The
8-68 byte input bound is not itself semantic SID validation or an AppContainer
identity proof. Synthetic fixtures are not actual machine SID evidence.

Successful composition retains the ownership wrapper. Closing destroys the
attribute list before freeing its referenced SID. Failed partial composition
with uncertain attribute teardown retains both attribute evidence and SID,
without freeing a potentially referenced buffer. Failed/uncertain free retains
the pointer and blocks automatic retries. Caller reconciliation after UNKNOWN
remains required; no reconciler or launch integration is supplied.

Injected derive must return newly owned storage or raise with its own partial
allocation evidence. Arbitrary pointers are not safe native validation inputs.
This helper does not implement that native allocation contract or validate the
injected collaborator's honesty. The free collaborator uses exact True success;
a future native adapter must translate FreeSid's NULL success, not BOOL-cast it.

[Microsoft derivation contract](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deriveappcontainersidfromappcontainername)
requires FreeSid for returned storage.
[GetLengthSid](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getlengthsid)
requires prior validity checking.
[FreeSid](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-freesid)
returns NULL on success. These are API design references, not native test proof.

Derivation and equality do not prove an existing profile, correct ACLs, network
denial, child token identity or runtime isolation. Those requirements remain OPEN,
along with actual native SID binding, process creation/admission/capture and the
separate native containment qualification envelope.

## Bounded Verification

Pinned stage2-v2 Python; process/network and filesystem tripwires plus
nonlive_report_host; fresh .pytest-ea4e92s-sid-focused-a/result.xml.
Seven test files: sid_ownership, windows_attributes, creation_attributes,
windows_job, containment_lifecycle, parser_source, static_binary_inspection.
25 new SID fixtures + 114 predecessors = 139 passed / 0 failed, 0.48 seconds.
Both tripwire counts zero. Full working-tree qualification is pending.

No native Windows API, parser/SDK/receiver/model execution, profile/ACL mutation,
GPU/ComfyUI, deletion, staging, commit, push or production activation performed.
No full-green or native-containment claim is made.

## Working-Tree Broader Gate

Full tests/hermes_core/ fake-only gate used the same pinned Python and three
guard/report plugins, with the six unchanged separately governed OS-test
deselections. Fresh .pytest-ea4e92s-sid-full-a/result.xml:
3734 passed / 35 raw failed / 6 deselected / 104 subtests passed, exit 1,
137.70 seconds. Exact sorted classname::name comparison with the clean committed
00ff4eff baseline report: 35 unchanged, added 0, resolved 0.
34 process attempts denied; filesystem tripwire events 0.
JUnit SHA256: d58fee7062ada2455c1a2c4d9c3bfb9c9f34d45fccca0ed4e009ce6134bb929d.

Classification: WORKING-TREE NO-NEW-REGRESSIONS PASS / RAW GATE NOT GREEN.
Three new candidate files remain uncommitted. No existing tracked source edited.
Next source checkpoint: scoped review and staged-tree qualification, then clean
committed qualification before an exact-commit remote checkpoint. No native
execution or profile/security mutation is authorized by this evidence.

## Source Review Correction

Review found exception-metadata duck typing could mistake SID validation errors
carrying an unrelated prepared field for uncertain attribute teardown. Three
new validation-phase tests reproduced this before the fix (3 failed, 33
deselected, both tripwire counts zero). The helper now recognizes the specific
UnknownAttributeCleanup exception instead. Ordinary validation errors release
the owned SID and preserve their original exception; actual uncertain attribute
teardown still retains SID storage and prevents automatic retry.

Added invalid derive-pointer, derive-exception evidence and post-composition
attribute-cleanup failure coverage. No assertions or predecessor contracts
weakened. Final bounded working-tree suite: 36 SID cases + 114 predecessors =
150 passed / 0 failed, 0.67s, both tripwire counts zero; fresh
.pytest-ea4e92s-sid-review-green/result.xml. Earlier 139-test and full results
predate this review fix; broader requalification is required before staging.

Post-review full fake-only gate completed with the same six separately governed
OS-test deselections: 3745 passed / 35 raw failed / 104 subtests passed,
157.53 seconds. Exact failed-node comparison with committed 00ff4eff baseline:
35 unchanged / added 0 / resolved 0. JUnit SHA256:
1859708af4600f54f475ae9fb3cc3111ca03add3cb5b11ba4bd921516cbfbb1c.
Classification: REVIEWED WORKING TREE NO-NEW-REGRESSIONS PASS / RAW GATE NOT
GREEN. The exact three-file candidate may proceed to staged-tree qualification.
