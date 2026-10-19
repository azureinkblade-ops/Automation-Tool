# EA-4E.92NM medium pipe label design decision

Status: DESIGN APPROVED ONLY / NATIVE QUALIFICATION HOLD.
Parent: `3bc0e64a9670bfae70d87020f831b65aa7fd4614`.
Profile: accepted 92DE local-container profile only.

The user approved a medium-integrity mandatory label for the protected
challenge pipe as a design choice on 2026-10-19. This may let the ordinary
medium-integrity app write to a pipe created by an elevated issuer while
retaining `NO_WRITE_UP` against lower-integrity clients. It also lowers the
pipe's mandatory boundary compared with an elevated creator's default; the
owner, protected DACL, same-account owner rights, independent app-process
binding, one-shot challenge, and replay controls must still exclude other
medium callers. The label must not be low, absent, or silently defaulted.

The source-only proposed SACL fragment is `S:(ML;;NW;;;ME)`, with expected
readback SID `S-1-16-8192` and policy `0x00000001`. It is a proposal for
native qualification, not a claim that the elevated creator can set it on
the pipe or that the limited app can then connect. At the 92NM checkpoint,
the source-only 92NL screen did not inspect this SACL; the following 92NN
checkpoint adds that static check. Neither result proves the created pipe.

Before a protected issuer can qualify, freeze the complete owner/DACL/SACL
descriptor and creation flags, compile and hash the exact candidate binary,
and obtain separately bounded authorization for an elevated creator and
linked limited inert client. Read back the created object's owner, protected
DACL, and mandatory label. Prove specific-rights client write and deny
generic write, second instance, WRITE_DAC, WRITE_OWNER, descriptor change,
and a lower-integrity client. Any mismatch is HOLD. No UAC/native probe,
issuer authorization, Docker action, receiver/model call, or production
activation is authorized by this design decision.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_mandatory_label_ace
