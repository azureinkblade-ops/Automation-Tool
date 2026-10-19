# EA-4E.92NO protected pipe creator source candidate

Status: NON-LIVE SOURCE CANDIDATE / OPEN NOT INVOKED / PRODUCTION HOLD.
Parent: `c7bb48a7e552c69f2b268bcd20e1dbd4eb933e55`.
Profile: accepted 92DE local-container profile only.

`tools/Ea4eProtectedPipeCreatorCandidate.cs` proposes one server-side
`CreateNamedPipeW` path with a random issuer-generated name, explicit
protected DACL, `O:BA`, one narrow app-SID write grant, SYSTEM/admin grants,
and the 92NM-approved medium `NO_WRITE_UP` SACL. It requests the first
instance, one instance total, local-only clients, overlapped message mode,
512-byte buffers, and a non-inheritable handle. The proposed descriptor
must pass the 92NN static screen before `Open` can be called.

The template fixture invokes only `BuildSddl`; it never calls `Open`.
Focused template and adjacent descriptor tests: 37 passed, 0 failed in
the current tree. This is not a protected-pipe installation or effective
access check. The exact app SID must come from the approved local app-host
context and actual connected client, not this Codex process or caller text.
`Open` still needs exact native source/binary qualification, immediate
owner/DACL/SACL readback, limited-token positive and negative probes,
one-message lifecycle, and exact-handle cleanup before it can contribute
to an issuer. A failure to set the proposed owner or label is HOLD, not
permission to remove the control.

The accepted 92MK local app-host profile already has the default-disabled
`app.py` inspection hook from 92MN; the strict 92ME independent launcher
is not silently required by this profile. The protected Docker issuer,
production grant store, and bounded real receiver/model authorization
remain separate. No UAC, native pipe creation, app launch, issuer claim,
Docker mutation, Kilo/OpenCode/model, GPU/ComfyUI, or production activation
occurred in this checkpoint.
