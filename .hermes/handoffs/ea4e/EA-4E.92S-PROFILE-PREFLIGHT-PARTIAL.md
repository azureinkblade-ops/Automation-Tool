# EA-4E.92S Profile Preflight - Partial Implementation

Date: 2026-09-15
Governing synchronized baseline: 561e56fd39c28749fffa097dc349b7e72b8dd62c
Status: IMPLEMENTED / TESTS PENDING / UNCOMMITTED
Native containment: NOT QUALIFIED

Three new candidate files only. The injected preflight requires independent pins
for profile name, SID bytes, canonical local storage path, volume serial and
128-bit file identity. It accepts only an exact immutable snapshot with no
reparse-point indication and returns an immutable reviewed identity.

The contract does not inspect the machine, open handles, follow paths, create a
profile, modify ACLs, or invoke native functions. A future native inspector must
collect race-resistant path identity without following reparse points and close
its own handles. Matching this value contract does not prove inspection freshness,
ACLs, token identity, storage permissions, network denial or process isolation.

No production integration, native call, process launch, parser/SDK/receiver/model,
GPU/ComfyUI or activation. Targeted and broader fake-only verification pending.

## Bounded Verification

The initial run stopped at collection because a raw-string fixture ended in a
single backslash. After that syntax-only correction, one test failed because the
fixture constructor used None as its default and therefore could not represent a
literal None inspection result. An explicit private sentinel corrected the test
fixture without weakening production checks.

Final bounded suite: 45 profile-preflight cases + 182 predecessors = 227 passed /
0 failed, 0.50s. Process/network and filesystem tripwire events zero; fresh
.pytest-ea4e92s-profile-focused-c/result.xml. Full working-tree fake-only gate
pending. Three candidate files remain unstaged and uncommitted.

Full working-tree fake-only gate with six separately governed OS-test
deselections: 3822 passed / 35 raw failed / 104 subtests passed, exit 1,
116.33 seconds. Exact failure-identity comparison with committed 561e56f baseline:
35 unchanged / added 0 / resolved 0. 34 process attempts denied; filesystem
tripwire events 0. JUnit SHA256:
b8f9340a466cf16182aac31ec4cf1bdf87a3599bc5a19b25e23ffb78489a3fdd.

Classification: WORKING-TREE NO-NEW-REGRESSIONS PASS / RAW GATE NOT GREEN.
Exactly three new files remain unstaged and uncommitted. Next checkpoint is
scoped source review and staged-export qualification. Actual profile inspection,
ACL/storage access and containment remain unqualified.

## Source Review Correction

Review found `ntpath.normpath` alone accepted Windows path aliases and invalid
components despite the helper's canonical-path contract. Eight focused cases
reproduced acceptance before inspection: trailing space/dot, alternate-data-stream
colon, reserved DOS names, control characters and wildcard/reserved characters.
The validator now requires an alphabetic drive and rejects those component forms,
including COM1-COM9 and LPT1-LPT9 stems. Added a non-letter-drive fixture.

Final post-review bounded result: 54 profile cases + 182 predecessors = 236 passed
/ 0 failed, 0.51s, both tripwire counts zero; fresh
.pytest-ea4e92s-profile-review-green/result.xml. No predecessor assertion or
identity pin was weakened. Post-review broader requalification is pending.

Post-review full fake-only gate: 3831 passed / 35 raw failed / 104 subtests
passed, exit 1, 112.07s. Exact failure comparison with committed 561e56f:
35 unchanged / added 0 / resolved 0. 34 process attempts denied; filesystem
tripwire events 0. JUnit SHA256:
ca226d821e08404692a205ea462f26430fd81cb964a81f1fd0f3df5812d61f02.

Classification: REVIEWED WORKING-TREE NO-NEW-REGRESSIONS PASS / RAW GATE NOT
GREEN. Exactly three files may proceed to staged-export qualification.
