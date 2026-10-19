# EA-4E.92NW pipe SACL privilege source candidate

Status: SOURCE-ONLY CANDIDATE / NATIVE EXECUTION HOLD.
Governing parent: `63c6104a1a7aa5117b581e84b5ddbf98d26dc05b`.

The 92NV fixture now opens its process token with adjust/query rights,
resolves `SeSecurityPrivilege`, requests the enabled attribute, checks both
the API return and `GetLastError`, and restores the previous state in a
`finally`-backed disposable scope. The protected pipe is created and read
only inside that scope. Failure to enable or restore denies the probe.

This corrects a source-level prerequisite for requesting SACL access on
the pipe handle. It is **not** evidence that the operator token possesses
the privilege, that the marshaled structures match the native ABI, or that
the restore path works on this host. Only inert argument/denial modes ran.
Focused source and adjacent 92NT/92NO tests: 27 passed, 0 failed.

The earlier locally built 92NV executable is stale and must not be used.
Any future native readback attempt requires a fresh committed-source build,
SHA-256 pin, exact invocation/operator/deadline, and separate one-shot
authorization. The fixture still lacks limited-client access and denial
probes, durable one-shot accounting, installation, and an issuer. No UAC,
native pipe, Docker mutation, receiver/model call, production activation,
GPU, or ComfyUI action occurred.

API basis:
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-adjusttokenprivileges
