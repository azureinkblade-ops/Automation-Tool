# EA-4E.92LR retained app-handle observation

Status: NON-LIVE / READ-ONLY HANDLE OBSERVATION / PRODUCTION HOLD.
Baseline: `a4add443ebfdb8fb7ae63fac5ff78a147377b81e`.

The 92LQ owner now retains the process creation time in its launch receipt.
On each `resolve_live`, an optional process API path queries the retained
handle through the existing Windows retained-handle API rather than trusting
the launcher's own observation. PID, creation time, and liveness must match
the launch receipt exactly. Query failure, malformed return, or drift makes
the owner UNKNOWN and bars automatic retry. An observed exit permits only
closing that retained handle. The fake-only observer path remains for tests;
production must not treat it as independent authority.

Changed: `tools/ea4e92lq_app_instance_owner.py` and
`tests/hermes_core/test_ea4e92lq_app_instance_owner.py`.
Focused owner tests: 32 passed, 0 failed. Non-pipe adjacent gate: 114 passed,
0 failed. Nine inert named-pipe fixture tests returned
`PIPE_CONNECTION_UNAVAILABLE` inside the filesystem sandbox and passed 9/9
when rerun in the previously used unsandboxed test context. No application
or receiver was launched for these tests.

This does not prove the receipt came from a trusted creator. A caller could
still supply a handle acquired by PID lookup, and an unprotected launcher
could fabricate package identity. The independently installed launcher,
approved package/dependency closure, real app-token/pipe binding, protected
issuer, and exact mapped-byte proof remain open. No real Kilo/OpenCode/model,
Docker mutation, GPU, ComfyUI, or production activation occurred.
