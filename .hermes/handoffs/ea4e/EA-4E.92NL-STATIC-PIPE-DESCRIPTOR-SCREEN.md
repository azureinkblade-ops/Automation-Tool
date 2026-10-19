# EA-4E.92NL static pipe descriptor screen

Status: NON-LIVE CANDIDATE / NO PROTECTED PIPE QUALIFIED.
Parent: `5b90a7518f3b89e9a84eb317839bd5b4be10a9d7`.
Profile: accepted 92DE local-container profile; strict 92AT remains separate.

`tools/Ea4eProtectedPipeDescriptorScreen.cs` parses a proposed SDDL through
`RawSecurityDescriptor`. It rejects a missing/app-owned owner, absent or
unprotected DACL, an app allow other than one exact `FILE_WRITE_DATA` ACE,
selected broad trustees, and mutation rights for non-SYSTEM/non-admin
trustees. Unsupported ACE shapes fail closed. The only non-denial result is
`CANDIDATE:STATIC_ONLY`, deliberately not PASS or AUTHORIZED.

The 20 synthetic cases in
`tests/hermes_core/test_ea4e92nl_descriptor_screen.py` compile the candidate
with the installed .NET Framework C# compiler and exercise these rejections.
They create no pipe, token, issuer, container, receiver, or model process.
They do not prove Windows effective access, trustee group membership, owner
rights, mandatory integrity, deny-ACE effects, instance or remote flags,
readback of a created object, or the final issuer SDDL. In particular,
`CANDIDATE:STATIC_ONLY` may still be unusable or unsafe at runtime.

This source screen cannot be used to issue authority or activate production.
Next: freeze the exact owner/SDDL/label and native creator/client binary,
review them, then request a separately bounded UAC/native qualification
of the actual elevated creator and linked limited client. Denials and exact
cleanup are required. No automatic real Kilo/OpenCode or Docker action follows.
