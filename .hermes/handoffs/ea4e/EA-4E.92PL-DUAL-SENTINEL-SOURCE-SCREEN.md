# EA-4E.92PL Dual-Sentinel Source Screen

The pure `Ea4eDirectory2HandleResultCandidate.Screen` rejects both zero and
`INVALID_HANDLE_VALUE` (`-1`) without invoking `CreateDirectory2W`. Every
other pointer value is only `CANDIDATE:NON_SENTINEL_ONLY`, not proof of a
valid directory handle or a successful creation. This addresses the immediate
misclassification risk noted in 92PK but does not resolve the documented
W/A failure-contract discrepancy or the five-versus-six-argument example.

Focused fake fixture: 5 passed. Adjacent matrix: 366 passed, 3 existing
skips. All 48 `Ea4e*.cs` sources compiled into an ignored diagnostic DLL;
the DLL was not installed. No P/Invoke was added to this candidate.

The native adapter remains HOLD pending a separately reviewed ABI, immediate
`GetLastError` capture on either sentinel, ownership-safe retained-handle
construction, descriptor/label and persistent-ACL volume observation, and a
new exact one-shot authorization for any mutating native probe. A non-sentinel
value cannot be promoted to a successful install by this screen alone.
There was no directory/ACL mutation, receiver/model call, GPU/ComfyUI call,
or production activation. Strict 92AT mapped-byte proof remains REJECT/HOLD.
