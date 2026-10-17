# EA-4E.92LF local pipe client-token observation

Status: NON-LIVE API PROBE ONLY / PRODUCTION HOLD.
Parent baseline: `0a3a0a22b9f4b3202eb3ecc2009f6fe1fde6b393`.

The read-only `Ea4ePipeClientTokenCandidate` checks an already-read local
named-pipe client on the same server thread. It requires successful
`ImpersonateNamedPipeClient`, opens that thread's token, rejects an
identification-only or elevated token, compares the observed SID with an
independently supplied expected SID, and calls `RevertToSelf` in `finally`.
A revert failure terminates the process. The API returns observation or
denial only; it has no issuer, Docker, receiver, model, or network capability.

The fixture creates a same-process local client, writes one byte, and tests
matching SID, wrong SID, and three malformed expected SIDs. The handshake is
bounded. In the filesystem sandbox all five cases initially failed at the
pipe connection step: the client timed out before token observation. The
same finalized fixture outside that sandbox passed all five cases in 0.43s.
The adjacent non-live snapshot gate passed 38 tests with three permission
skips in 2.17s, including these five cases. No failed sandbox run is counted
as a passing native qualification.

This proves only the local Windows API behavior for a same-process fixture.
It does not prove an actual app connection, independently retained app
instance identity, explicit pipe DACL or remote-client exclusion, ceremony
challenge binding, token duplication and lifetime through `AccessCheck`,
protected issuer installation, or a real receiver handoff. The prior exact
mapped-byte requirement is unchanged. No UAC ceremony, authorization,
Docker mutation, Kilo/OpenCode call, model invocation, GPU activity, or
production activation occurred. The next slice must implement and fake-test
the protected pipe server and independent app-instance binding before any
bounded live ceremony can be proposed.
