# EA-4E.92PB announcement namespace preflight

Status: NON-LIVE HOLD / NO INSTALLED NAMESPACE.
Governing parent: `3caee2b77da7785da86310119c7d7e694a934204`.
Profile: accepted 92DE trusted local-container host only; strict 92AT remains separate.

Read-only observation on 2026-10-20: `C:\ProgramData\Hermes` and
`C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1` do not exist. No
installation or access-control mutation was attempted. The machine-wide
known-folder path has not been independently resolved against a trusted
installer manifest in this checkpoint. A caller-provided path, environment
variable, current directory, or per-user temp directory cannot substitute.

The installed-root gate must fail closed until a separately reviewed installer
creates each missing component under the machine-wide ProgramData known
folder. It must bind the trusted manifest to the resolved known-folder path,
exclude reparse components, set and read back exact owner, protected DACL and
high/no-write-up label on retained handles, and prove the intended medium
token can read/traverse but cannot create, write, rename, delete or change
security. A path string or static SDDL check alone is not that proof. Existing
objects with unexpected identity or security are HOLD, not repaired in place.

The installed root is only one prerequisite. The creator-to-coordinator
channel, retained file-identity/byte/descriptor observations, durable one-use
ledger, limited-client pipe check, and full 92NK gate remain open. No native
installer, pipe, file, Docker mutation, receiver, model, GPU, ComfyUI or
production action is authorized by this note. No earlier one-shot native
approval is reusable.

Next non-live work: implement a source-only exact known-folder/manifest path
comparison with denial tests, then review the installer and retained-handle
observations before requesting a new bounded native probe. A successful fake
comparison must not be reported as an installed namespace.
