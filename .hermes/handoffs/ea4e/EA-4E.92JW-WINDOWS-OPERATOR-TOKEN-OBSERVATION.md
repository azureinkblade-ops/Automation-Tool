# EA-4E.92JW Windows operator token observation

Status: NON-LIVE READ-ONLY TOKEN CHECK / NO CEREMONY OR AUTHORITY.
Governing predecessor: `9a6f83fb04a552b551e21312d80fb8a1b8f82c13`.

David selected the current administrator account with visible UAC consent
for a future separate Docker-mutation issuer. This checkpoint adds only a
Windows access-token observer. It reads the current process token user SID
and `TokenElevation` state through Windows APIs, compares the SID with a
trusted-policy value supplied by a future separate ceremony, and denies
invalid/mismatched/non-elevated/unavailable observations. It never launches
an elevated process, prompts for UAC, issues authorization, or calls Docker.
The current non-elevated Codex process was read-only checked and denied as
`OPERATOR_TOKEN_NOT_ELEVATED` for its own SID.

The design follows Microsoft documentation for
[GetTokenInformation](https://learn.microsoft.com/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation),
[TokenElevation](https://learn.microsoft.com/windows/win32/api/winnt/ne-winnt-token_information_class),
and [running only a separate privileged process with UAC](https://learn.microsoft.com/en-us/windows/win32/secbp/running-with-administrator-privileges).

Focused tests: 9 passed. Adjacent fake-only 92I/92J/HJ/HV/HY ladder:
370 passed before commit. Positive token outcomes were mocked, not observed
from an elevated process. An elevated token plus matching SID would still
be only one precondition, not a Docker permit: a trusted policy SID source,
distinct ceremony process, durable one-shot issuer/store, current authority,
and mutation claim remain unimplemented. Production remains HOLD.
