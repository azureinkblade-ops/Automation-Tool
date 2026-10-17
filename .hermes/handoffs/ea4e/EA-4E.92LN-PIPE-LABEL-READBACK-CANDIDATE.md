# EA-4E.92LN pipe mandatory-label readback candidate

Status: NON-LIVE NATIVE FIXTURE PASS / PRODUCTION HOLD.
Baseline: `fea321e9f223455a4278baf7d7f5cdf43d67bd5f`.

The new candidate reads `LABEL_SECURITY_INFORMATION` from an already-open
pipe handle with `GetSecurityInfo(SE_FILE_OBJECT)`, then enumerates the
returned mandatory-label ACE. It reports the integrity SID and policy mask,
an unlabeled object, or a denial. It does not set an integrity label, create
an issuer pipe, bind an app process, or grant execution authority. This
label-only query is distinct from requesting the full audit SACL: the
documented label-query right is `READ_CONTROL`; full SACL retrieval requires
`ACCESS_SYSTEM_SECURITY` and the appropriate privilege. An actual protected
creator must still prove its handle carries the rights needed for readback.

Native fixture: a temporary same-token .NET named pipe. The current Codex
low-integrity fixture reported `OBSERVED:S-1-16-4096:00000001`, i.e. a low
mandatory label with NO_WRITE_UP. This is not evidence of the label that an
elevated issuer-created pipe will have. A null handle was denied without
calling the Windows API.

Focused command:

`python -m pytest -q -p no:cacheprovider --basetemp=output/ea4e92ln-adjacent-20261017 tests/hermes_core/test_ea4e92ln_pipe_integrity_label.py tests/hermes_core/test_ea4e92lj_pipe_client_binding.py tests/hermes_core/test_ea4e92lg_pipe_client_process.py tests/hermes_core/test_ea4e92lf_pipe_client_token.py`

Result: 16 passed, 0 failed. The 92LN dedicated test is 2 passed, 0 failed.
No staged-only or committed-tree test has yet been claimed for this WIP.

Next gate remains the 92LK/92LM bounded elevated-creator and linked
limited-app-token native probe. It must read back owner, DACL and mandatory
label from the retained protected pipe handle, compare the actual app
token, and run the positive and negative access matrix. The current
same-token fixture cannot close that gate. No UAC prompt, authorization
issuance, Docker mutation, Kilo/OpenCode/model call, GPU/ComfyUI activity,
or production activation occurred. Production remains HOLD.

API basis:

- https://learn.microsoft.com/en-us/windows/win32/secauthz/security-information
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control
