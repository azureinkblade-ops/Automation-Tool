# EA-4E.92KF explicit SQLite durability mode

Status: NON-LIVE / CANDIDATE STORE DEPENDENCY ONLY.
Governing source: `8e6f6e62a5d93892396d064c7aca6d9d7d47ed1f`.

The protected-SQLite wrapper now requests `journal_mode=DELETE` and
`synchronous=FULL` on each connection and rejects a different effective
setting. The test confirms the reopened database's journal mode, while the
constructor verifies its connection-local sync mode. The wrapper source
SHA-256 at qualification is
`BC13BD2CE3D9A01EF719C8504D414D17D6791878E3A59EB5B358AA80022F9328`.

Focused 92KC/92KD/92KE tests passed 31/31. The adjacent fake-only ladder
passed 429/429 before commit. A committed-tree rerun remains required.
This does not solve the external-anchor crash gap or protect files from a
local administrator; it does not attest a protected installation or issue
a real one-shot permit. No UAC, Docker mutation, Kilo/OpenCode receiver,
model, GPU, ComfyUI, or production activation occurred. Production remains
HOLD.
