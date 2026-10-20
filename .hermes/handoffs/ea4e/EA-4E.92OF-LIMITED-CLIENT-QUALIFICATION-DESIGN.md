# EA-4E.92OF limited-client qualification design

Status: NON-LIVE DESIGN ONLY / NO NATIVE CLIENT OR ISSUER RUN.
Governing parent: `3ef5345ceb1899c7d6362e2a54ea55ce56e02bf7`.
Profile: accepted 92DE trusted local-container app host, not strict 92AT.

## Qualified predecessor and open claim

92OE established one bounded structural owner/group/DACL/SACL/label
readback and cleanup through the pinned native fixture. It did not establish
the effective rights of a medium-integrity client. The protected issuer,
Docker mutation, receiver execution, model invocation, and production
activation remain HOLD.

## Two-process fixture contract

1. The medium-integrity coordinator retains the exact medium client process
   handle, PID, creation time, SID, elevation type, and deadline. It must
   launch the client itself; a child launched by the elevated creator would
   inherit the wrong token unless a separately qualified token-lowering
   mechanism existed. The elevated creator is a distinct, one-shot process.
2. The elevated creator alone chooses the ceremony-bound random pipe name,
   explicit SDDL, first-instance/one-instance policy, remote rejection,
   message mode, and 512-byte frame bound. It retains the exact server
   handle. Name announcement to the trusted coordinator is not authority:
   any mutation of the name or client-supplied security policy is denied.
   The announcement channel and its exact binding must be reviewed before
   implementation or native use.
3. Before allowing a client connection, the creator verifies its own token
   and `SeSecurityPrivilege`, reads back the actual descriptor on its handle,
   and checks the expected owner, DACL, label, and instance policy. Failure
   closes the exact handle and stops the ceremony.
4. The medium client attempts separate fresh opens for `GENERIC_WRITE`,
   `WRITE_DAC`, and `WRITE_OWNER`; each must fail specifically from access
   denial. `PIPE_BUSY`, missing pipe, timeout, or an open that unexpectedly
   succeeds is HOLD, not proof of ACL denial. The client must never use an
   elevated or impersonated server token for these probes.
5. A second-instance attempt must fail while the first server instance is
   retained. Because `FILE_FLAG_FIRST_PIPE_INSTANCE` can itself cause
   `ERROR_ACCESS_DENIED`, that result alone does not prove the DACL denied
   `FILE_CREATE_PIPE_INSTANCE`. The readback DACL and a separately reviewed
   effective-access/token check must support that narrower claim.
6. Only after negative checks may the same retained medium client request
   `FILE_WRITE_DATA` (`0x00000002`) with `CreateFileW` and `OPEN_EXISTING`.
   It sends one bounded canonical frame, remains connected, and is observed
   through the server's same handle after the read. The server compares the
   kernel client PID/creation time and impersonated limited token to the
   coordinator-retained process and expected app SID, then applies the
   canonical parser. No bytes are accepted on denial or ambiguity.
7. The creator closes the exact pipe handle, the coordinator waits for the
   exact client and creator processes, and a ceremony-specific namespace
   scan must find no pipe. Uncertain cleanup is HOLD, with no automatic
   retry. One run may issue no authorization and may launch no receiver.

## Qualification order

First implement source-only access-mask and denial-classification tests with
inert inputs. Then review the two-process launcher, announcement binding,
and process/token lifetime contract. Only a fresh exact authorization may
permit one native fixture with pinned source commit, executable hashes,
operator SID, client token pair, arguments, deadline, and one-attempt budget.
Wrong-account and remote-client tests are separate gates. A pass here would
not qualify a trusted installed issuer or production execution.

Windows API basis:

- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew
- https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants
