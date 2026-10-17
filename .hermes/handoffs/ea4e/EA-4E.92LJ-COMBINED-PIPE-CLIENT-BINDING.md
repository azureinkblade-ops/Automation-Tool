# EA-4E.92LJ combined pipe-client observation

Status: NON-LIVE API COMPOSITION ONLY / PRODUCTION HOLD.
Parent baseline: `67822e5bbbd65c8751d9df8f7d65e2eea6286b6a`.

The read-only candidate composes the existing 92LG connected-client process
object check and 92LF client-token SID/limited-token check on the same pipe
handle after one message read. It checks the retained process object before
and after the token observation. A failure at any step denies; the token
candidate retains its fail-closed `RevertToSelf` behavior. It does not issue
or consume authority or perform an action on behalf of the client.

The native local fixture passed matching process/SID, wrong SID, malformed
SID, and a real live wrong-process handle: 4/4. The combined 92LJ/92LI/
92LF/adjacent protected-path gate passed 47 with three permission skips in
2.80s. The native pipe fixture ran outside the filesystem sandbox, whose
local pipe connection had timed out during 92LF. The wrong-process handle
is obtained from the already-running pytest parent for test purposes only.

This does not prove a protected pipe DACL, remote-client rejection,
challenge and ceremony binding, independently owned app-instance handle,
token duplication or lifetime through `AccessCheck`, protected issuer
installation, exact byte witness, or an authorized live agent handoff.
The read-only composition must never be interpreted as an approval witness.
No UAC ceremony, Docker mutation, Kilo/OpenCode call, model invocation,
GPU activity, or production activation occurred. Production remains HOLD.
