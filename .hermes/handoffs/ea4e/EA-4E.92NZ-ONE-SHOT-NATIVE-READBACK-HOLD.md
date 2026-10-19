# EA-4E.92NZ one-shot native readback result

Status: HOLD / one-shot authorization consumed.
Governing source commit: `694eae831eaaecfb93aaba12fc90371824e3e9e3`.
Executable: `output/ea4e92ny-native-readback-probe.exe`.
Verified executable SHA-256: `854d33d7c15816e7805ed68bfecc01a40e3bbc374573ae981369ba860e9fce9a`.
Expected operator SID: `S-1-5-21-1542204473-82821690-3590615374-1001`.

The separately approved readback-only attempt used ceremony
`cc5490c0-46ce-403d-81c6-7cad8b7131f0`, UTC deadline
`2026-10-19T21:29:29Z`, and one elevated process, PID `26692`.
It exited `15`, the fixture's `READBACK` stage. That code does not distinguish
a returned readback denial from an exception during readback or pipe disposal.
It is not evidence that owner, DACL, SACL, or limited-client rights passed.

Post-run inspection found PID `26692` absent and zero pipes matching the
ceremony-specific `ea4e-issuer-cc5490c046ce403d81c67cad8b7131f0-*`
prefix. No retry was attempted. The authorization is consumed.

The historical 92NX HOLD remains unchanged. The 92NK protected-pipe gate,
trusted creation, strict 92AT mapped-byte invariant, and production readiness
remain open. No client, Docker mutation, Kilo/OpenCode receiver, model,
credential, GPU, ComfyUI, or production activation was exercised in this
attempt. Further native execution requires a new exact bounded authorization.
