# EA-4E.92UX staged-context consumption gate

Date: 2026-10-28 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE / INDEPENDENT REVIEW REQUIRED / NATIVE HOLD / PRODUCTION HOLD

A source-only context manager now requires the exact returned tar naming
pattern inside a caller-selected canonical staging directory. It checks
regular-file type, bounded size, and device/inode identity before opening
and on the opened handle. It reads the tar from that handle, verifies the
expected Dockerfile bytes, member order/type/metadata, and six pinned model
hashes, then rewinds and yields the same handle to a future bounded caller.
It checks handle identity and size again after consumption. No Docker
invocation is present in this module.

Focused strict fake/source tests passed (131/131), including wrong-directory,
same-size replacement, size change, and tampered-member denial. No real
model bytes, Docker build, container, GPU, receiver, handoff, or production
activation occurred.

This is not a complete launcher or immutable snapshot. The module does not
validate Windows ACLs, prevent a privileged concurrent writer from changing
bytes after verification, establish a hard wall deadline for a 9.3 GB scan,
or reconcile Docker side effects. A future launcher must enforce those
boundaries and consume only the yielded handle. Independent review and an
exact bounded authorization are required before real staging or build.
Production remains HOLD.
