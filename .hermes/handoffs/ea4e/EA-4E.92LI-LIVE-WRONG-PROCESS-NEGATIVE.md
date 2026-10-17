# EA-4E.92LI live wrong-process negative

Status: NON-LIVE TEST CORRECTION / PRODUCTION HOLD.
Parent baseline: `75906aba77f47562fc8aed21d1b29dd791109877`.

EA-4E.92LG's first native fixture covered a matching process handle and
invalid handles, but not a different live process. The fixture now accepts
the already-running pytest parent's PID for a negative case, opens its real
process handle, and presents that handle as the expected app process while
the pipe client remains the fixture process. The candidate denies with
`CLIENT_PROCESS_MISMATCH`. No new helper process or privileged action is
introduced beyond the existing local fixture.

Focused 92LG fixture: 5 passed. Combined 92LI/92LF/adjacent protected-path
gate: 43 passed, three permission skips, 2.45s. The native pipe fixture
ran outside the filesystem sandbox, whose local pipe connection had timed
out during 92LF. The original 92LG evidence remains its historical result;
this is an additional negative, not a retroactive change to that count.

Opening a process by PID is permissible in this negative test only. It is
not a production app-instance owner. Production must receive a process
handle retained by an independently protected launcher, as frozen in 92LH.
No UAC ceremony, Docker mutation, Kilo/OpenCode call, model invocation,
GPU activity, or production activation occurred. Production remains HOLD.
