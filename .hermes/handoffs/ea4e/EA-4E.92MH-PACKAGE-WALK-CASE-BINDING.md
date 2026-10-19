# EA-4E.92MH package walk case binding

Status: NON-LIVE CORRECTION / PRODUCTION HOLD.
Parent baseline: `868ee536ccdf43e576dac072d90962835bc99afa`.

The 92MG diagnostic walker compared expected file and directory paths using
case-insensitive keys. That could report a match for spelling that the 92MF
exact-case manifest comparator rejects. The walker now rejects conflicting
expected directory casing and requires each observed file and directory
spelling to match the manifest exactly. Existing missing/extra and byte checks
remain unchanged.

Changed: `tools/Ea4ePackageClosureWalkCandidate.cs` and
`tests/hermes_core/test_ea4e92mg_package_closure_walk.py`.
Focused: 13 passed, 2 skipped. Adjacent topology, byte snapshot, pure
manifest, app-owner, import inventory, and text-recovery gate: 112 passed,
7 skipped, 0 failed, one inherited `app.py` invalid-escape warning.

The output remains `MATCH:UNPROTECTED_WALK_ONLY`, not an authoritative
package observation. No protected root/write exclusion, atomic namespace
snapshot, complete dependency manifest, mapped-image byte proof, issuer,
real receiver/model, Docker mutation, or production activation was established.
Production remains HOLD.
