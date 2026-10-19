# EA-4E.92OB one-shot readback screen result

Status: HOLD / one native run consumed.
Governing source commit: `90d1ce5443ea12b2f7d9298c6c876e4c10c224e5`.
Executable: `output/ea4e92oa-native-readback-probe.exe`.
Verified executable SHA-256: `2c9082607de8c8a800e428428b2a9f20b6d62a978262316c24c211e5c4982221`.
Expected operator SID: `S-1-5-21-1542204473-82821690-3590615374-1001`.

The first launch command was blocked before `Start-Process` returned a PID.
Inspection found zero matching processes and zero pipes for its ceremony
`6eb418e8-e651-4b5a-8e32-425d946a013b`. This was not a native run.

With the same pinned source and executable, the separately approved elevated
readback-only run used ceremony `e3071c7e-6e9d-495d-a6a7-1ed49da0a18e`,
UTC deadline `2026-10-19T21:37:21Z`, and PID `92988`. It finished once
with exit `31`, the fixture's `DENY:DESCRIPTOR_SCREEN` classification.
That classification is returned when the readback's secondary descriptor
screen does not return `CANDIDATE:STATIC_ONLY`; the exact secondary denial
was not preserved. The process was absent afterward and no pipe matching
the ceremony-specific prefix remained. No retry was attempted.

The 92NZ HOLD remains unchanged. This result does not prove the actual
owner/DACL/SACL or any limited-client rights. The 92NK gate and production
readiness remain HOLD. No client, Docker mutation, Kilo/OpenCode receiver,
model, credential, GPU, ComfyUI, or production activation was exercised.
Another native run requires a new exact one-shot authorization.
