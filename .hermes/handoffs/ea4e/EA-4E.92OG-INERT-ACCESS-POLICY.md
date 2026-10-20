# EA-4E.92OG inert limited-client access policy

Status: NON-LIVE SOURCE-ONLY / NO NATIVE CLIENT PROBE.
Governing parent: `d8ba8a1aefdf78309827b26b5a2a96a5f1d8bbe7`.

The policy fixes four request masks: `FILE_WRITE_DATA` (`0x00000002`),
`GENERIC_WRITE` (`0x40000000`), `WRITE_DAC` (`0x00040000`), and
`WRITE_OWNER` (`0x00080000`). It classifies an allowed specific-write open
as handle-only, not as an authenticated frame; any negative-probe open as
unexpected success; `ERROR_ACCESS_DENIED` as observed-only; and busy,
missing-pipe, and other errors as non-ACL evidence. The second-instance
case remains separately governed because the first-instance flag can itself
produce access denied.

The fixture compiles the policy and calls only its inert mask and
classification methods. It has no P/Invoke, pipe open, token change,
client process, or issuer. The dedicated and adjacent working-tree matrix
passed 148/148; its staged source export passed 21/21. Native limited-client rights, same-handle process/token
observation, trusted issuer installation, and production remain HOLD.

API basis: https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
