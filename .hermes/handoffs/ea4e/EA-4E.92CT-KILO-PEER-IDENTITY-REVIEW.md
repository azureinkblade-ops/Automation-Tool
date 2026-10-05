# EA-4E.92CT Kilo gateway peer-identity review

Status: NON-LIVE REVIEW / PRODUCTION PEER IDENTITY HOLD
Baseline: `0b710461c25e4bba749927cd600f077ec086b524`

## Finding

The proposed gateway receives Kilo's OpenAI-compatible request over loopback
HTTP. A bearer token delivered in `KILO_CONFIG_CONTENT` proves possession of
that token, not that the sender is the authorized Kilo process. A fresh port,
short TTL, and one-call durable budget limit exposure and replay, but do not
exclude another process running under the same Windows account from obtaining
the token or sending the one allowed request first.

Windows named-pipe ACLs and `GetNamedPipeClientProcessId` apply to a named-pipe
connection, not to the separate TCP connection made by Kilo's current HTTP
provider. Adding a named-pipe side channel would not bind the later HTTP
request to that pipe client without another independently qualified mechanism.
The current Kilo provider has no demonstrated named-pipe transport. Therefore
a pipe PID check is not accepted as process-bound proof for this route.

## Recommendation and acceptance boundary

Treat other same-user processes as untrusted until the operator explicitly
chooses a different local adversary model. Under that model, the current
loopback bearer design is insufficient for production upstream forwarding.
Do not issue an upstream credential to Kilo or accept a production gateway
request on the strength of token possession alone.

The next implementation design must demonstrate an OS-enforced isolation or
peer-authentication boundary compatible with Kilo's actual HTTP transport.
It must show, with negative tests, that an unrelated same-user process cannot
read the local token or consume the gateway's sole send budget. A dedicated
restricted identity/container with enforced local and outbound access is one
candidate, not a qualified solution. Keep the upstream credential gateway-only
and retain the existing durable claim-before-send, no-refund semantics.

The separate 92CR dummy-provider shape probe may be considered under its own
exact one-shot authorization; it does not close this production peer-identity
hold. The 92S exact mapped-byte proof remains an independent HOLD. No Kilo
process, listener, real provider, model, GPU, or ComfyUI operation occurred in
this review.

## Platform references

- [Named Pipe Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)
- [GetNamedPipeClientProcessId](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid)
- [Named Pipes](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipes)
