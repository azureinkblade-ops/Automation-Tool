# EA-4E.92OV creator peer source candidate

Status: NON-LIVE SOURCE CHECK / NATIVE CHANNEL HOLD.
Governing parent: `a4cfa4882926184ec5bfb15cd5ab92eb360d1f1d`.

The source-only `Ea4eCreatorPeerBindingCandidate` accepts a caller-retained
connected pipe instance and the caller-retained elevated launch process
handle. It requests the pipe client's PID, the launch process PID and
creation time, and a zero-time wait on that same process handle. Its pure
screen requires nonzero identity, exact expected PID/creation-time match,
client PID equal to the retained launch PID, and an unsignaled launch handle.
The fixture compiles the candidate and exposes only inert screen inputs;
there is no native observation, UAC launch, or pipe-connection CLI.

This is one observation, not completed channel authentication. The caller
must independently establish its expected launch identity, pin the image
and token, verify the pipe instance policy, and re-observe process liveness
after the bounded exchange. It must also qualify the elevated client's
verification of the server; this helper is one-sided. A reused PID, process
exit, API failure, missing handle, or source mismatch is HOLD without retry.
No nonce or attestation was transmitted, and no native file/pipe, receiver,
model, Docker, GPU, ComfyUI, or production action occurred.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocessid
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes
