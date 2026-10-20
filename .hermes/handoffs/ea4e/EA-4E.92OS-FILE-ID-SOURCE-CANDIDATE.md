# EA-4E.92OS retained file-ID source candidate

Status: NON-LIVE SOURCE CHECK / NATIVE OBSERVATION HOLD.
Governing parent: `6993e728f9e526034c076c219f634b6fca26c0f1`.

The source-only `Ea4eAnnouncementFileIdentityCandidate` accepts a
caller-owned retained file handle and requests `FileIdInfo` (`0x12`) from
`GetFileInformationByHandleEx`. It represents the 64-bit volume serial as
16 lowercase hexadecimal digits and the 16 file-ID bytes in returned byte
order as 32 lowercase hexadecimal digits. Zero or malformed identity fails
closed. The inert fixture compiles this code and exercises only the info-
class and formatting screens; it exposes no native handle-read CLI.

This source does not open the installed namespace, observe a real file ID,
prove descriptor ownership/label, authenticate a creator attestation, or
compare creator and medium retained handles. It cannot authorize pipe
connection, receiver/model activity, or production. The native `Read` method
requires a fresh exact bounded authorization before use in any fixture.

Official API basis:

- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info
