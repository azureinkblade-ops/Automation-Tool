# EA-4E.92S Windows SID Adapter - Partial Implementation

Date: 2026-09-15
Governing synchronized baseline: d655b62a03234f73b2ab2e5c3f85a53e6c43c72a
Status: IMPLEMENTED / TESTS PENDING / UNCOMMITTED
Native containment: NOT QUALIFIED

Three new candidate files only. The adapter lazily binds DeriveAppContainerSid-
FromAppContainerName, IsValidSid, GetLengthSid and FreeSid when explicitly built
without injected collaborators. Tests inject all DLL functions and memory reads;
they perform no native call.

The adapter tracks pointers it received from successful derivation, requires
validity before bounded length, requires that exact length before reading, and
removes ownership only after translating FreeSid NULL success to exact True.
Failed release becomes uncertain and cannot be retried automatically. Failed
derivation with a non-null output preserves explicit partial-allocation evidence
and blocks unsafe release; it requires future reconciliation rather than guessing.

This module does not create or confirm an AppContainer profile, alter ACLs, create
a token or process, or prove filesystem/network isolation. It is not wired into
production or the containment lifecycle. Targeted and broader verification remain
pending. No staging, commit, push or production activation is authorized here.

## Review and Bounded Verification

Initial bounded suite passed 181 tests, then source review found two ownership
ambiguities. A successful derive returning an already-owned pointer did not mark
that pointer uncertain, and a FreeSid exception did not lock retries. Two focused
tests reproduced both defects before correction (2 failed / 30 deselected; both
tripwire counts zero). Duplicate storage now raises PartialSidDerivation and marks
the pointer uncertain. A FreeSid exception likewise marks it uncertain before
preserving the original exception. Neither path can retry release automatically.

Final bounded suite: 32 adapter cases + 150 predecessor cases = 182 passed / 0
failed, 0.43s, process/network and filesystem tripwire events zero; fresh
.pytest-ea4e92s-windows-sid-review-green/result.xml. No assertions or predecessor
contracts weakened. Full working-tree fake-only regression remains pending.

Full working-tree fake-only gate with the same six separately governed OS-test
deselections: 3777 passed / 35 raw failed / 104 subtests passed, exit 1,
118.78 seconds. Exact failed-node comparison with committed d655b62 baseline:
35 unchanged / added 0 / resolved 0. 34 process attempts were denied by the
guard; filesystem tripwire events 0. JUnit SHA256:
bacb34ff17c0915082b2fd8f9c86c7c165338e7d443700006447e1a1f387e79e.

Classification: WORKING-TREE NO-NEW-REGRESSIONS PASS / RAW GATE NOT GREEN.
Exactly three new files remain uncommitted and unstaged. Next checkpoint is
scoped staged-tree review/qualification. Native DLL calls, profile verification,
process creation and actual containment remain unqualified and unexecuted.
