# EA-4E.92OD mandatory-label readback query

Status: NON-LIVE SOURCE-ONLY / NATIVE RETRY HOLD.
Governing parent: `f585e41fab6a9eea475e7d57ca854b46eb2d1f55`.

The 92OB native run exited with a descriptor-screen denial. The 92OC source
preserves its exact secondary reason for a future run but did not itself run
natively. The existing `GetSecurityInfo` request asked for owner, group,
DACL, and SACL (`0x0000000f`) but omitted the separately defined
`LABEL_SECURITY_INFORMATION` flag (`0x00000010`). Windows documents that
flag as referencing the mandatory integrity label. This checkpoint adds it
to the readback request (`0x0000001f`) and tests that mask through an inert
CLI path. This is a plausible missing-label cause, not a retrospective
diagnosis of the 92OB result.

Documentation: https://learn.microsoft.com/en-us/windows/win32/secauthz/security-information

The inert and adjacent working-tree matrix passed 127/127, and the staged
source export passed 49/49. No native mode,
protected pipe, client, Docker mutation, Kilo/OpenCode receiver, model,
credential, GPU, ComfyUI, or production activation was exercised. The 92OB
HOLD and the wider 92NK and production gates remain open. A future native
run requires a new exact binary pin and separate one-shot authorization.
