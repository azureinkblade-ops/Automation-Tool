# EA-4E.92S Windows Profile Adapter - Partial Implementation

Date: 2026-09-15
Governing synchronized baseline: 15eede49531126363aebe8505715334b03687dc7
Status: IMPLEMENTED / REVIEWED / WORKING NO-NEW-REGRESSIONS PASS / UNSTAGED
Native containment: NOT QUALIFIED

Three new candidate files only: a lazy/injected Windows profile-inspection
adapter, 32 fake-only cases and this evidence. Existing tracked source remains
unchanged.

The adapter derives and validates an existing AppContainer SID, converts it to
its string form, resolves the existing AppContainer storage folder, opens that
directory with FILE_FLAG_BACKUP_SEMANTICS and FILE_FLAG_OPEN_REPARSE_POINT, and
queries FileAttributeTagInfo plus FileIdInfo. It returns a value-only snapshot
containing SID bytes, path, volume serial, 128-bit file identity and reparse
status. The previously qualified profile preflight remains responsible for
matching that snapshot against independent pins.

All tests inject SID and DLL interfaces. No real Win32 function was invoked.
The adapter cannot create/delete profiles, change ACLs, launch a process, access
the network, invoke a receiver/model, or activate production.

## Review Corrections

Initial focused result was 28 passed. Source review found that a failed native
call returning a non-null output did not establish safe release ownership. Three
red cases reproduced partial SID derivation, SID-string conversion output and
folder-path output. The corrected adapter does not speculatively free uncertain
outputs; it preserves their identities, releases only known-owned resources,
enters a sticky reconciliation-required state and blocks retry.

Independent staging review found one related edge: a native call could report
success while returning an invalid non-null output pointer. Two red cases showed
that the adapter would attempt speculative release. Invalid non-null SID-string
and path outputs now enter the same uncertain state without invoking a release
function on the malformed address. Final focused result: 32 passed / 0 failed /
both tripwire counts zero, 0.10s.

The exact API shape follows Microsoft documentation: GetAppContainerFolderPath
returns caller-freed folder storage; directory handles require
FILE_FLAG_BACKUP_SEMANTICS; FILE_FLAG_OPEN_REPARSE_POINT disables normal reparse
processing; FileIdInfo combines volume serial and 128-bit file identity.

## Qualification

Complete post-review 92S bounded suite: 32 new + 249 predecessor tests = 281
passed / 0 failed, 0.56s. Process/network and filesystem tripwire counts were
both zero.

Final post-review full working-tree fake-only gate with six separately governed
OS-test deselections: 3876 passed / 35 raw failed / 104 subtests passed, exit 1,
109.41 seconds. Exact failure-identity comparison with committed 15eede4 baseline: all
35 unchanged / added 0 / resolved 0. The guard denied all 34 attempted process
launches; filesystem events were zero. JUnit SHA256:
4795ffdbbec808bf36b8f4cd3d7f360323dbcb2d6bf91b7bec56b990c7b16966.

Prohibited-capability scan found no subprocess/process creation, profile
creation/deletion, ACL mutation, network, receiver/model, GPU or ComfyUI surface.

State: IMPLEMENTED / REVIEWED / BOUNDED PASS / WORKING NO-NEW-REGRESSIONS PASS /
UNSTAGED / UNCOMMITTED / RAW GATE NOT GREEN. Next checkpoint is exact three-file
source review and staged-export qualification. Real profile inspection,
profile/ACL mutation, native process creation, parser/SDK/receiver/model execution
and actual containment remain unexecuted and separately governed.
