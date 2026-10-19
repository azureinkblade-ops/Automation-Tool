# EA-4E.92MG read-only package closure walk candidate

Status: NON-LIVE CANDIDATE / PRODUCTION HOLD.
Parent baseline: `9fe066445dbce64c726a9d86c36322ceb35d6936`.

This candidate walks a caller-named Windows directory and compares its
observed file names and SHA-256 bytes with an explicit expected set. It
rejects missing and unexpected entries, invalid or colliding manifest paths,
reparse points, multi-link file leaves, and changed bytes. The topology
checker now has a separate directory-leaf entry point; its existing file-leaf
entry points retain their behavior.

Changed source: `tools/Ea4eProtectedPathTopologyCandidate.cs`,
`tools/Ea4ePackageClosureWalkCandidate.cs`.
Added fixture and tests:
`tests/hermes_core/fixtures/ea4e92mg_package_closure_walk_probe.cs`,
`tests/hermes_core/test_ea4e92mg_package_closure_walk.py`.
Focused gate: 10 passed, 2 skipped. Adjacent gate including 92KY topology,
92LC byte snapshot, and 92MF pure manifest: 51 passed, 7 skipped, 0 failed.
The skipped tests require Windows filesystem privileges or facilities that
were unavailable in this test context.
The five staged blobs matched the tested worktree. The staged-equivalent
gate, also including app owner, import inventory, and text recovery tests,
passed 109 with 7 skips and one inherited `app.py` invalid-escape warning.

The walker uses path enumeration followed by separate handle checks. It
does not hold a protected package root, establish ACL/write exclusion,
guarantee an atomic namespace snapshot, record complete file object
identities and byte lengths for the 92MF comparator, attest interpreter or
dependency closure, or bind the created image section to the reviewed bytes.
`MATCH:UNPROTECTED_WALK_ONLY` is diagnostic, never production authority.
No real app, issuer, receiver, model, Docker mutation, GPU, ComfyUI, or
production activation was run. Trusted creation and production remain HOLD.
