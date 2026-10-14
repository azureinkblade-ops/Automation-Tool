# EA-4E.92JY protected issuer deployment contract

Status: NON-LIVE CANDIDATE / NOT INSTALLED / NOT QUALIFIED.
Governing source: `49aa23eb8b16f2047df34e554268d3a0a7747f4c`.

## Trust boundary

The approved local profile trusts the administrator who confirms UAC and the
protected Windows installation, not a process or file controlled by the
ordinary app account. The current worktree grants that account FullControl.
Neither a worktree hash check performed by worktree code nor the 92JW token
observer loaded from that tree can issue Docker authority.

The first elevated executable must be the protected Windows PowerShell binary
at `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`, launched by
an explicit operator ceremony, not by the app request path. The prospective
issuer must be a self-contained script or a fully enumerated package in a
separately protected install directory. Its transitive runtime, imports,
configuration, native libraries, and store bootstrap must be enumerated and
pinned. The current Python request-builder graph is not an elevated closure.
No script from the worktree may be dot-sourced, imported, or executed with
elevation, including during installation.

## Installation candidate

1. An operator reviews the exact helper bytes and records their SHA-256 in an
   independent approval channel. A hash merely read from the mutable source
   tree is not an approval witness.
2. A separate elevated installer copies candidate bytes as inert data into a
   newly created versioned directory below a protected base. It does not run
   the candidate. Its own code must already be protected or be an explicitly
   reviewed inline operator command; it cannot import from the worktree.
3. After copy, hash the destination bytes and compare them with the
   independently approved hash. A changed source during copy fails this
   comparison. Verify every transitive executable/library/configuration byte
   against the approved closure before any candidate execution.
4. Inspect the directory and every ancestor's effective DACL, owner, and
   reparse status from handles. Ordinary users and the app identity must have
   no write, replace, delete, ownership, or DACL-change path to the closure.
   Inherited allows and group membership count. A string comparison of
   `C:\Program Files` paths or an `icacls` display alone is insufficient.
5. Publish the qualified version only after the destination hash and ACL
   checks pass. Do not overwrite a currently qualified version in place;
   promotion and rollback each need their own reviewed identity and audit.

The protected issuer must recheck its own location, version hash, operator
SID/elevation, installation/store ID and epoch, request hash, action, source
commit, expiry, and predecessor claims before issuance. It must use a fixed
working directory, scrub user-controlled module search paths, and reject
relative/unapproved dependencies. It must not obtain authority from a caller
supplied `verified` flag or from the existing activation ceremony. The
distinct one-shot Docker-mutation store and claim semantics remain those of
92JU and are not implemented by this document.

## Qualification and stop conditions

Fake-only tests must cover a writable parent, permissive inherited group,
reparse swap, altered destination byte, missing transitive file, changed
store epoch, wrong operator SID, non-elevated token, stale source commit,
duplicate issue, and rollback. A clean-path test must verify that the helper
uses only the protected closure. A live install or UAC prompt needs a new
exactly bounded authorization that names source and destination hashes,
installation path, operator, store, and cleanup/rollback procedure. Docker
network or container mutation needs a separate action-specific authorization
after that qualification. No permission for Kilo/OpenCode execution, model
invocation, GPU, ComfyUI, or production activation follows from an install.

This checkpoint performs no installation, UAC, Docker mutation, receiver
call, model invocation, or activation. Production remains HOLD.
