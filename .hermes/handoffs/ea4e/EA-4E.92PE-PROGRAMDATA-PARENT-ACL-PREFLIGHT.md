# EA-4E.92PE ProgramData parent ACL preflight

Status: READ-ONLY INSTALLATION-RACE HOLD.
Governing parent: `da3e7b044dd26cfa158064c9644fde0806b4c9d6`.
Profile: accepted 92DE trusted local-container host only.

Read-only Windows ACL observation on 2026-10-20:

- `C:\ProgramData` exists as a non-reparse directory in the ordinary file
  attributes reported by PowerShell. Its owner is `NT AUTHORITY\SYSTEM`; its
  DACL is protected from inheritance.
- Explicit allow ACEs include SYSTEM and Administrators FullControl,
  BUILTIN\Users ReadAndExecute/Synchronize, and BUILTIN\Users Write with
  ContainerInherit. The last ACE prevents treating this parent as an
  administrator-exclusive creation boundary. `CREATOR OWNER` also has an
  inherit-only full-access ACE for created descendants.
- `C:\ProgramData\Hermes` and the planned `Hermes\EA4E\IssuerAnnouncements\v1`
  root remain absent. No creation, ACL edit or deletion was attempted.

This ACL listing is not an effective-access result for the exact medium
token, nor a retained-handle descriptor/label observation. It is enough to
reject a plan that assumes exclusive elevated control while creating the
missing first child by name and securing it later. A local actor may race or
preplant the name; a successful path-based creation call alone would not
prove the resulting handle is the reviewed object. Existing unexpected
objects must be HOLD, not adopted or repaired in place.

Before a native installation proposal, review and source-pin a creation
mechanism that handles the initially absent child without an unprotected
window, binds each newly created child to a retained handle, denies
reparse/replacement and inheritance drift, applies and reads back the exact
owner/protected DACL/high label, then proves actual medium-token read and
mutation denials. If the mechanism cannot close the creation race, choose a
different already protected root or a separately administered host; do not
relax the gate implicitly. A new exact one-shot authorization is required
for any native install/probe. Earlier pipe readback approvals are consumed.

The 92PC path-value screen and 92PD known-folder lookup remain non-authorizing.
No issuer, receiver/model, Docker, GPU, ComfyUI or production action occurred.
Full 92NK, trusted installation and production remain HOLD.
