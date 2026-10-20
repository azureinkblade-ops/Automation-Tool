# EA-4E.92OP label-readback contract correction

Status: NON-LIVE REVIEW / INSTALLED ANNOUNCEMENT HOLD.
Governing parent: `7722313b4b7251106140561d1539b7ddb36110b9`.
Profile: accepted 92DE trusted local-container host only.

92OL assigned directory and record owner/DACL/label readback to the medium
coordinator. That is not a valid unconditional requirement. Windows requires
`ACCESS_SYSTEM_SECURITY` on the opened handle to read SACL information, and
the documented way to obtain it enables `SeSecurityPrivilege` before open.
The mandatory integrity label is a SACL ACE. A filtered medium app token
must not be assumed to hold that privilege. A medium `GetSecurityInfo`
failure is HOLD, not evidence that the label is absent or secure.

The corrected candidate divides observations by authority:

1. The separately installed, trusted elevated installer reads back the
   namespace directory owner, protected DACL, and high/no-write-up label on
   its exact retained directory handle. Installation is not yet authorized
   or qualified.
2. The trusted elevated creator opens/creates the record with
   `ACCESS_SYSTEM_SECURITY`, scopes enabled `SeSecurityPrivilege`, and reads
   back record owner, DACL, and label on its own retained handle before
   announcing it. The 92OM creator mask is only a source candidate.
3. The medium coordinator requests no `ACCESS_SYSTEM_SECURITY`. It reads
   owner/DACL with `READ_CONTROL` on its retained directory/record handles,
   proves its actual limited-token read access and denied mutation, and
   binds the record bytes to the retained creator process and ceremony.
4. Cross-process file identity must be compared on the creator and medium
   handles. Current 92OJ v1 JSON does not carry the creator's volume/file ID
   or a bound attestation of its label readback, so it cannot alone close
   that binding. A reviewed v2 record/attestation or equivalent retained
   protocol is required before a native two-process qualification.

None of these observations may be collapsed into a Boolean supplied by the
request. Trust in the elevated creator is limited to the accepted 92DE
profile and does not satisfy strict 92AT mapped-byte proof. A failed
privilege enable, missing SACL/label, mismatch across handles, medium write
success, or uncertain cleanup remains HOLD without retry. No existing native
approval is reusable for a new probe.

Next non-live gate: source-review the elevated file descriptor readback and
v2 creator-to-coordinator file-identity record before attempting installer
or limited-client qualification. No native file/pipe, Docker mutation,
receiver/model, GPU, ComfyUI, or production action occurred here.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
