# EA-4E.92S Probe Admission Contract - Partial Implementation

Date: 2026-09-16
Governing synchronized baseline:
`184bfd1d9b0186ca813549bca52d838e1ff5ea41`

State: IMPLEMENTED / REVIEWED / FAKE-ONLY PASS / UNSTAGED / UNCOMMITTED

## Scope

Added a value-only probe admission contract and synthetic tests. The contract
separates the reviewed policy from the presented candidate and requires exact
equality before returning immutable admission evidence. It binds request/probe
identity, runtime/bootstrap/request artifacts, request-root identity, existing
AppContainer profile identity, ordered argv, credential-free environment and
fixed budgets.

The validator receives caller-supplied immutable bytes and checks exact size and
SHA256. It performs no file read, process creation, resume, network operation,
profile/ACL mutation or probe execution. Its result is not launch authority.
Native handle/path race protection remains a later boundary.

## Review Corrections

The first implementation assumed obsolete ProfileSnapshot field names; the
focused run reproduced that mismatch and the validator was aligned to the
committed profile contract. The next focused run passed 64 cases.

Source review then found two policy gaps: hash-matched request bytes were not
semantically bound to request/probe identity, and the allowlisted environment
could omit or misroute required Windows/TEMP pairs. Canonical JSON validation
now rejects extra, mismatched, duplicate or noncanonical request data. The
environment must contain exactly SystemRoot, TEMP, TMP and WINDIR in canonical
order, with matched Windows roots and matched temporary roots inside the exact
request-owned directory. Request-root name, staged-artifact ancestry, distinct
artifact paths and exact fixed budgets are also required.

## Verification

Final focused result: 71 passed / 0 failed / 0.14 seconds. Complete EA-4E.92S
bounded result: 474 passed / 0 failed / 0.72 seconds. Both guarded focused runs
had process/network and filesystem tripwire counts zero.

Full fake-only Hermes Core gate: 4069 passed / 35 raw inherited failures / 6
unchanged deselections / 104 subtests passed, exit 1, 107.90 seconds. Exact
failure-identity comparison with the committed broker baseline found all 35
unchanged, added 0 and missing 0. All 32 attempted process launches were denied;
filesystem events 0. JUnit SHA256:
`121ee15d05dcbdf2698bc12aa50689e2709ebec22f02d8a38987f7532e45ba16`.

## Boundary

No dedicated executable bootstrap exists yet; tests use synthetic bytes only.
No native adapter, process, resume/capture path, network/filesystem probe,
parser, SDK, receiver, model, browser, GPU or ComfyUI activity was introduced or
executed. The next checkpoint is exact three-file staged-export qualification.
Native containment remains NOT QUALIFIED.
