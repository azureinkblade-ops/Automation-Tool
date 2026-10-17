# EA-4E.92LG local pipe client/process observation

Status: NON-LIVE API PROBE ONLY / PRODUCTION HOLD.
Parent baseline: `80ce1f35698e51db9dde820347f84cec6a049e92`.

The read-only `Ea4ePipeClientProcessCandidate` queries the process ID of an
already-connected named-pipe client and compares it with a caller-retained,
live process-object handle. Null and known pseudo handles are rejected. A
signaled or invalid expected process object is rejected. The candidate
neither opens the process itself nor accepts a caller-supplied PID as
identity. The expected handle's independent owner is not implemented here.

The same-process local fixture passed its matching-handle, null-handle, and
two pseudo-handle cases: 4/4. With 92LF and adjacent protected-path snapshot
tests, the non-live gate passed 42 with three permission skips in 2.43s.
The machine's .NET Framework compiler rejected an initial throw expression
in the fixture; it was changed to compatible switch syntax before the green
run. All named-pipe tests ran outside the filesystem sandbox, whose local
pipe connection had timed out during 92LF.

This test does not cover a different live process or prove that the caller
retained a handle from an independently approved app instance. PID equality
alone is not authority. A future protected server must own the process
handle before the ceremony, bind the expected app runtime and challenge,
create the pipe with an explicit restrictive DACL and remote rejection,
then combine that binding with the observed client token before any
privileged decision. The 92KT fake store and 92KX review data remain
untrusted for live issuance. No UAC ceremony, Docker mutation,
Kilo/OpenCode call, model invocation, GPU activity, or production
activation occurred. The exact mapped-byte requirement is unchanged.
