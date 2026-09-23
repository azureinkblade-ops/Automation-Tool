# EA-4E.92AD Suspension-Proof Contract Roll Design

## Disposition

NON-LIVE DESIGN CANDIDATE / no implementation or native probe authorized.

This design supersedes only the unimplementable independent
`is_thread_suspended(thread_handle)` proof requirement in the EA-4E.92S
pre-resume contract. All other containment, ownership, cleanup, replay,
budget, and host-binding requirements remain unchanged. It does not change
`tools/ea4e92s_pre_resume.py` or any existing test in this checkpoint.

## Why the roll is necessary

The current `verify_pre_resume_containment()` demands four queries. Job
membership, active count and AppContainer SID have concrete query candidates.
The fourth asks whether the primary thread is suspended, independently of the
creator's `SuspendedCreationResult.suspended` Boolean. The documented
`GetThreadInformation` classes do not expose suspend count or state.
`SuspendThread` and `ResumeThread` change the count and are not read-only
verification. Treating a zero-timeout wait or a creator Boolean as an
independent suspend-state query would make the claimed evidence false.

Windows does document that a primary thread created with `CREATE_SUSPENDED`
does not start executing until another thread resumes it. The implementable
proof is therefore *trusted creation provenance plus controlled resume
authority*, not an independent read-only OS-state observation. This is an
inference from the documented API contract, not a measured live result.

## Proposed proof contract

1. The reviewed native creation adapter, and no caller-supplied Boolean,
   fixes `CREATE_SUSPENDED` and the required creation-time job/AppContainer
   attributes in its exact `CreateProcessW` invocation.
2. Its canonical creation receipt binds the exact adapter/source identity,
   request ID, attribute-owner identity, job handle, process/thread handles,
   PID/TID, creation flags, and a one-shot resume authority held by the same
   lifecycle owner. The receipt is in-memory; raw handles are never persisted.
3. A successful `CreateProcessW` return is insufficient alone. The retained
   handles must still pass the existing independent job-membership, active
   count, and AppContainer SID checks, plus process/thread identity checks.
4. From creation return through the pre-resume verdict, the lifecycle owner
   remains in `CREATED_SUSPENDED`. No code path may call `ResumeThread`,
   transfer or duplicate the primary-thread handle, or release the creation
   attributes. The owner serializes verification and any later resume/cleanup.
5. The pre-resume verifier consumes the exact creation receipt and validates
   the owner state and flag provenance instead of calling
   `is_thread_suspended`. It must label the result as creation-provenance
   evidence, not an independent current suspend-state measurement.
6. A denied or unknown verdict cannot become a positive resume permission.
   Cleanup must use only the exact owned process/job/handles. An ambiguous
   close or termination remains sticky unknown with no automatic retry.
7. A later, separately reviewed resume operation may consume the one-shot
   authority only after the positive verdict and exact identity recheck.
   Replays, concurrent calls, owner replacement and post-cleanup resume deny.

The trust boundary is the reviewed native creation adapter and its retained
lifecycle owner. An arbitrary injected backend or fake receipt cannot prove
real suspension. The design assumes no external privileged actor resumes the
thread through another handle; the native implementation review must assess
handle access/duplication exposure and record this residual assumption. If
that assumption cannot be defended for the target host, the native probe
remains on hold.

## Required implementation tests

- Exact `CREATE_SUSPENDED` and extended-startup flag set; omission or flag
  drift denied before any positive pre-resume verdict.
- Creation receipt binds the exact returned handles and PID/TID; swapped,
  duplicated, zero, stale, or cross-request identities deny.
- Pre-resume membership, active count and AppContainer SID mismatch deny.
- A backend-provided `suspended=True` without trusted provenance denies.
- Resume attempted before verdict, twice, concurrently, after cleanup, or
  from another owner denies without calling the injected resume function.
- Verification exception, cancellation or cleanup ambiguity leaves sticky
  unknown; no retry, fallback launch or fabricated clean result.
- A fake-only happy path proves the ordering of creation, verification and
  one authorized resume, but must not be described as native qualification.
- The full EA-4E.92S bounded and guarded Hermes Core gates must show no new
  failure identities; staged and committed tree runs remain required.

## Non-goals and next gate

This checkpoint adds no process launcher, `WinDLL` call, token query,
`ResumeThread` call, live watcher wiring, runtime activation or NQ probe.
Implementation requires a separate narrow source authorization and exact
contract roll against the current tests. A native probe still requires the
frozen Stage 3 host/runtime/profile/argv/fixture identities and an exact
bounded authorization. Fake-only success is not production readiness.

## Primary API references

- https://learn.microsoft.com/en-us/windows/win32/procthread/suspending-thread-execution
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getthreadinformation
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ne-processthreadsapi-thread_information_class
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-suspendthread
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread
