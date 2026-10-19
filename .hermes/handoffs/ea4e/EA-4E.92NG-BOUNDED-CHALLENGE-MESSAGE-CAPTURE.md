# EA-4E.92NG bounded challenge message capture

Status: NON-LIVE BYTE-CAPTURE CANDIDATE / PRODUCTION HOLD.
Parent: `10b654ad41dfb7ba11bee4091670172ea810d940`.

`Ea4ePipeChallengeMessageCandidate` accepts only an already-connected
message-mode server pipe and a 1-5000 ms deadline. It makes one asynchronous
read into a 513-byte buffer, accepts only a complete nonempty message of at
most 512 bytes, and returns copied bytes without a client-identity or
authorization claim. A deadline cancels and disposes the pipe; an observed
read completion is distinguished from unknown completion. A later caller
must treat both outcomes as denial and reconcile any unknown completion.

The inert fixture creates a random local disposable pipe and covers complete
message, 513-byte oversize, deadline, and disconnect. A first fixture run
failed because explicitly setting ReadMode on a read-only message-mode server
handle returned access denied. Removing that redundant setter left the
candidate's fail-closed `ReadMode` check intact; the corrected fixture passed
4/4. No protected pipe, independent issuer, app-instance launcher, or live
receiver was created.

Still open: owner/DACL/integrity-label and remote-client policy/readback;
same-connection last-read process/token observation; challenge expectation
comparison using the 92NE canonical parser; extra-message/replay policy;
retained app-handle recheck; durable one-shot accounting; native binary and
installation qualification. A captured message is not an authenticated
sender. Strict 92AT exact mapped-byte proof remains REJECT/HOLD.

Microsoft's `IsMessageComplete` contract applies after a read in message
mode; cancellation still requires completion observation:

- https://learn.microsoft.com/en-us/dotnet/api/system.io.pipes.pipestream.ismessagecomplete?view=netframework-4.8.1
- https://learn.microsoft.com/windows/win32/api/ioapiset/nf-ioapiset-cancelioex
