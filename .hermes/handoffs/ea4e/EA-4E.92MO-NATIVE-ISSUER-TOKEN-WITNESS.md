# EA-4E.92MO native issuer token witness

Status: NON-LIVE CANDIDATE / NOT AN ISSUER / PRODUCTION HOLD.
Parent: `a988412c318e6bed5b03f752bcc8cf02715fc0fa`.

`tools/Ea4eProtectedIssuerToken.cs` reads the current Windows process token
with `WindowsIdentity` and `GetTokenInformation(TokenElevation)`. It compares
the observed account SID and actual elevation with an expected SID. Invalid,
foreign, unavailable, or non-elevated observations deny. The expected SID
must eventually come from a separately protected, reviewed issuer policy;
passing an app-controlled value is not operator authority. The pure
comparison is exposed for negative tests only. No UAC prompt, grant issue,
store write, Docker command, receiver, or model capability is present.

The test probe compiles only the token source and probe fixture. Focused
tests: 7 passed. The adjacent Python token, complete grant candidate, and
v4 grant-store ladder passed 59/59 when `TEMP`/`TMP` and pytest base were
set to a fresh writable repository output directory for that command. An
initial repository-base run had one pre-existing fixture path requirement;
an initial sandbox system-temp retry could not create pytest directories.
Neither failure required a production change. The successful run performed
no elevation or live receiver/model work.

This witness is a necessary component of a protected issuer, not the issuer
itself. Installed binary/dependency identity, effective ACL and reparse
verification, independent trusted policy sourcing, durable issuance and
one-attempt accounting, and exact installation/live-action authorizations
remain open. The strict 92AT route is unchanged.
