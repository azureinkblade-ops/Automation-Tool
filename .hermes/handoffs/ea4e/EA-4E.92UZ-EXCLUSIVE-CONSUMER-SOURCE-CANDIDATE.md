# EA-4E.92UZ exclusive consumer source candidate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD / PRODUCTION HOLD

The consumer now fails closed outside Windows and uses a Windows file
handle opened for reading with read sharing only. This rejects concurrent
ordinary writer and delete opens while the handle is held. The same
handle is used for archive verification and later yielded to a future
caller. The post-yield identity check runs in a `finally` block.

Tar validation now checks the expected header offsets, six-member
inventory plus Dockerfile, uname/gname, exact expected archive length,
and zero-only trailing bytes. Focused strict fake/source tests passed
(137/137), including a six-file synthetic tar written by the existing
context writer, a same-size write attempt while the handle is held,
trailing data, truncation, metadata drift, and caller failure. No real
model bytes, Docker build, container, GPU, receiver, handoff, or
production activation occurred.

This source candidate does not prove a hostile privileged actor cannot
alter the file, that the private-directory ACL remains unchanged, or that
a future Docker process consumes only the held descriptor. A bounded scan
deadline and build-side-effect reconciliation are still absent. Docker's
`--network=none` build option limits `RUN` networking but does not alone
prove offline base-image resolution. An independently reviewed launcher,
separate exact native authorization, verified resulting image ID, and
later model and agent-handoff evidence remain mandatory. Production HOLD.
