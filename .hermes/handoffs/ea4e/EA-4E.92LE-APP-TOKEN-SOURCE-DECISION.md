# EA-4E.92LE app-token source decision

Status: NON-LIVE DESIGN / NO TOKEN SERVICE OR ISSUER IMPLEMENTED.
Baseline: `02a47c146b7c9b32876b3f27bc460c4996db987a`.

## Decision

The elevated operator token must not stand in for the ordinary app token
when checking access to an issuer installation. A UAC-linked limited token
is also insufficient by itself: it identifies the operator's linked logon
token, not necessarily the token, enabled groups, restricted SIDs, or
integrity context of the actual app connection. EA-4E.92LA/92LD observe
the current unelevated process only and cannot be imported as an elevated
issuer's app-token witness.

The candidate source is a short-lived, local named-pipe connection from the
actual app instance to a separately protected operator process. The pipe
is an identity-collection channel only. The protected server creates it
with an explicit restrictive DACL, bounded instance count and message size,
`PIPE_REJECT_REMOTE_CLIENTS`, and a unique ceremony-bound name. It reads
one challenge-bound message,
then calls `ImpersonateNamedPipeClient` and `OpenThreadToken` on that same
server thread. It requires a nonanonymous impersonation token with the
independently approved app SID and a limited/non-elevated identity. It
duplicates that exact token for the read-only `AccessCheck`, retains it
through the object-handle checks, and always calls `RevertToSelf` before
any operator/store operation. Failure to impersonate, open, duplicate,
validate, or revert the token fails closed and aborts the process. The
app's message body, claimed PID/SID, and requested action never establish
operator approval or a Docker mutation budget.

The future implementation must bind the pipe client to the expected app
instance independently of caller text. A reviewed app-instance owner must
retain the process identity and establish its source/runtime binding; a
client PID alone is not durable identity. If app-instance binding cannot be
qualified, the issuer cannot use the observed token. A separate operator
ceremony must still approve exact artifact bytes, store lineage, one action,
and expiry. The 92KT fake store and 92KX review data do not become trusted
merely because the pipe check passes.

## Required non-live qualification

- Wrong/missing app SID, anonymous or identification-only impersonation,
  elevated client, wrong ceremony challenge, extra message, and timeout deny.
- A failed impersonation cannot fall back to the server's elevated token.
  Revert failure terminates the server rather than continuing privileged work.
- Pipe ACL denies unrelated accounts and rejects remote clients; no default
  permissive pipe security or app-selected pipe name is accepted.
- Token handle lifetime spans every retained ACL observation. Closing or
  replacing the client connection cannot silently swap the token in use.
- Fake-only tests prove no issuance, Docker call, receiver/model invocation,
  or other privileged side effect on every denial path.
- A later separately bounded local native probe must verify the actual
  Windows token and pipe behavior. Fake tests alone cannot qualify it.

Microsoft documents named-pipe client impersonation as applying to the last
message read; failure leaves the server in its own context, so the return
value must be checked. It also documents explicit pipe security descriptors,
`OpenThreadToken`, `DuplicateTokenEx`, and `RevertToSelf` as the relevant
native boundaries:

- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-impersonatenamedpipeclient
- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openthreadtoken
- https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-duplicatetokenex
- https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-reverttoself

This decision does not roll the 92KZ/92LB access contract, install an
issuer, open a pipe, prompt for UAC, mutate Docker, call Kilo/OpenCode or a
model, or activate production. Production remains HOLD.
