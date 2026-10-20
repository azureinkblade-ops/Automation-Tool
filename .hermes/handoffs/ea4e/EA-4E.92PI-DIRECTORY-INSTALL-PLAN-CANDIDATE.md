# EA-4E.92PI directory install plan candidate

Status: SOURCE-ONLY VALUE PLAN / NATIVE INSTALLATION HOLD.
Governing parent: `26c056a87a3fad328c904b7bd172f2ae6fc8a558`.
Profile: accepted 92DE trusted local-container host only.

The value-only C# plan composes the 92PC known-folder/manifest path screen
and 92PH exact directory descriptor screen. It produces exactly four child
paths from the supplied ProgramData root, the protected owner/group/DACL
and high/no-write-up SDDL, `DIRECTORY_FLAGS_DISALLOW_PATH_REDIRECTS=1`,
`FILE_SHARE_READ|FILE_SHARE_WRITE` without delete sharing (`3`), and a
candidate retained-handle readback access mask `0x012200a1`. The latter
includes `ACCESS_SYSTEM_SECURITY`; its actual behavior and required scoped
privilege are not established by this pure plan. No request or environment
input may override the fixed components.

The function cannot authenticate either supplied path value or the app SID.
It does not inspect a volume, open ProgramData, create any child, apply a
descriptor, or prove a returned handle. Its fixture has no native create
route. Focused plan/directory/file tests passed 32/32; adjacent non-live
matrix passed 352 with 3 existing symlink skips. These are not production
or installation results.

Next gate: a separately reviewed, default-deny elevated installer candidate
must independently source the known folder, pinned manifest and operator/app
identity, check the volume/parent, scope privilege, create with security
attributes at the exact first-child path, retain and read back the returned
handle, and stop on collision or uncertainty. A source-only fixture must not
expose a native mode. Only a later pinned binary with a new exact one-shot
authorization may attempt native installation. Full 92NK, issuer,
receiver/model and production remain HOLD. No native directory, pipe,
Docker, GPU or ComfyUI action occurred.
