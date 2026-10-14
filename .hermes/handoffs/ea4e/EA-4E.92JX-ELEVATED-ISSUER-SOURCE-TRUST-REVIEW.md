# EA-4E.92JX elevated issuer source-trust review

Status: NON-LIVE REVIEW / ISSUER DEPLOYMENT HOLD.
Governing source: `ca97f7df7f0336e1b90dc036668089e88d5f82c6`.

The accepted local-Docker profile trusts local administrators, but the
ordinary app/Codex process is currently non-elevated. A read-only Windows
ACL check found that the working tree is owned by `DAVIDSPC\David` and
grants that user `FullControl`. The current process token check returns
`OPERATOR_TOKEN_NOT_ELEVATED`. Therefore an elevated helper that imports
Python modules directly from this worktree would execute same-user-writable
source after UAC consent. The new 92JW token check cannot protect its own
code if loaded that way. A matching SID/elevation observation is necessary
but insufficient for the independent issuer boundary.

The future Docker-mutation ceremony must execute a pinned helper from a
separately protected installation under the approved local trust model. A
candidate installation directory needs an administrator/SYSTEM-controlled
ACL, with ordinary users and the app identity denied write/replace/delete;
all transitive code, interpreter/runtime, configuration, and imports must
come from the same reviewed dependency closure. The elevated helper must
reject a changed committed source hash, request hash, expected operator SID,
or authority-store identity/epoch. It must not load code or configuration
from the current worktree, current directory, `PYTHONPATH`, or a mutable
user profile. A hash check performed solely by an unprotected launcher is
not a source-trust boundary.

Microsoft recommends keeping the main app at `asInvoker` and starting only
the privileged component with UAC, for example using `ShellExecute` with
`runas`: [Running with Administrator Privileges](https://learn.microsoft.com/en-us/windows/win32/secbp/running-with-administrator-privileges).
`C:\Program Files` was read-only inspected as a *candidate* protected base;
this review did not install anything or certify a final directory ACL.

Next non-live work: freeze the exact helper closure, install/upgrade/rollback
contract, path and ACL validator, and fake-only issuer/store tests. A later
separately bounded installation and UAC ceremony will require exact source,
path, operator, action, and audit identities. No UAC prompt, install,
issuer, Docker mutation, receiver, or model call occurred. Production HOLD.
