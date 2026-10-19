# EA-4E.92NF inert pipe read completion probe

Status: NON-LIVE TRANSPORT OBSERVATION / PRODUCTION HOLD.
Parent: `fefc2bafb8ffccb80b1f10e04e0b71ea97a95c61`.

An isolated .NET Framework 4.8 fixture created a randomly named, local,
asynchronous, disposable pipe. It exercised one-byte delivery, a pending
read, a partial read, and client disconnect. The fixture made no receiver or
model call and issued no authority. After a 150 ms pending-read deadline it
requested cancellation, disposed the exact pipe, and required read-task
completion within another 2 seconds before reporting an observed cancellation.

The first run inside the restricted sandbox failed all four cases before a
read because the client could not connect. The permitted native rerun reached
the read path. A test expectation was corrected after observing that a byte
pipe can complete a two-byte read with one byte; this is a transport property,
not a production defect. Final current-tree adjacent gate: 77 passed,
0 failed across 92NF, 92NE, and 92LQ.

This fixture does not implement a protected pipe, owner/DACL/integrity-label
checks, remote-client rejection, a canonical-frame read, extra-byte rejection,
same-connection client process/token binding, retained app-handle recheck, or
an independent issuer. The 92ND production contract therefore remains open.
The strict 92AT mapped-byte requirement remains REJECT/HOLD. Fake and inert
native observations do not establish production readiness.

Microsoft documents that every BeginRead requires EndRead and that native
CancelIoEx only requests cancellation; completion must be observed before
releasing the associated operation storage:

- https://learn.microsoft.com/dotnet/api/System.IO.Pipes.PipeStream.BeginRead
- https://learn.microsoft.com/windows/win32/api/ioapiset/nf-ioapiset-cancelioex
