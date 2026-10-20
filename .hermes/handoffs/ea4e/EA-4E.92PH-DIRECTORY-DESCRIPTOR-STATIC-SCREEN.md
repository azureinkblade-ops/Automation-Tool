# EA-4E.92PH directory descriptor static screen

Status: SOURCE-ONLY STRUCTURE CHECK / NATIVE INSTALLATION HOLD.
Governing parent: `128ce4be883b8a5303778d4c00085c0896437bb1`.
Profile: accepted 92DE trusted local-container host only.

The announcement descriptor candidate now has a separate directory mode.
It requires the intended app SID to have exactly `0x000200a1` (read control,
list directory, traverse, read attributes), versus the unchanged file mode's
`0x00020081`. Both modes require the existing exact Administrators owner and
group, protected three-ACE DACL, SYSTEM/Administrators full rights, and one
high/no-write-up label. Directory and file success markers are distinct.
Malformed or extra binary descriptor bytes remain fail-closed.

The inert fixture can exercise only SDDL and byte screening; it has no native
directory read or creation route. Focused directory plus existing file tests
passed 26/26. The adjacent non-live matrix passed 346 with 3 existing
symlink skips. These are static checks, not proof that a filesystem creation
applies the descriptor, that an elevated installer reads it from a retained
handle, or that the medium token has the intended effective rights.

Next: source-review the default-deny installer call, explicit security
attributes at creation, retained returned handle, label/ACL readback,
identity/reparse/collision handling and effective-token denials. A native
installation still needs a new exact one-shot authorization. No directory,
pipe, Docker, receiver, model, GPU, ComfyUI or production action occurred.
Full 92NK and production remain HOLD.
