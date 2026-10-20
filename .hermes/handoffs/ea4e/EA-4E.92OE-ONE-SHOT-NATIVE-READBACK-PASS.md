# EA-4E.92OE one-shot native readback result

Status: PASS / bounded structural readback only; 92NK and production HOLD.
Governing source commit: `48209d4b897110fe61efa3e58830b560073a07f8`.
Executable: `output/ea4e92od-native-readback-probe.exe`.
Verified executable SHA-256: `518c7a0dc064c3d49d4131bde72266bf77802bcd0c05b06d4b9766ae302224c6`.
Expected operator SID: `S-1-5-21-1542204473-82821690-3590615374-1001`.

The separately approved readback-only attempt used ceremony
`fc6506f6-185a-46ca-9097-1333306b22d4` and UTC deadline
`2026-10-20T13:42:35Z`. One elevated process, PID `191076`, finished
with exit `0`. On the pinned native-mode path, the fixture returns `0`
only after the current operator token check, scoped privilege enable,
protected pipe creation, `GetSecurityInfo` owner/group/DACL/SACL/label
readback, structural descriptor screening, pipe disposal, and privilege
restoration. Post-run inspection found PID `191076` absent and zero pipes
matching the ceremony-specific `ea4e-issuer-fc6506f6185a46ca90971333306b22d4-*`
prefix. No retry was attempted; the one-shot authorization is consumed.

This is a structural readback result, not a complete 92NK qualification.
No separate limited-client token attempted `FILE_WRITE_DATA`, generic
write, `WRITE_DAC`, `WRITE_OWNER`, or second-instance creation. No frame
was exchanged, issuer installed, authorization issued, Docker mutation,
Kilo/OpenCode receiver or model run, credential use, GPU/ComfyUI activity,
or production activation occurred. The strict 92AT mapped-byte route
remains separate and HOLD. The historical 92NX, 92NZ, and 92OB results
remain HOLD as recorded; this pass does not rewrite them.
