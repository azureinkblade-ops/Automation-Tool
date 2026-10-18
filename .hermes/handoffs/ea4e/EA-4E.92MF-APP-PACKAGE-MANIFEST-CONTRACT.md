# EA-4E.92MF app package manifest contract

Status: NON-LIVE QUALIFIED / PRODUCTION HOLD.
Parent baseline: `eda1ea63b049f5700887775444525da3c20f579f`.

`compare_package_inventory()` is a pure exact-set contract for a future
protected app-package enumerator. It compares canonical relative file
paths, lowercase SHA-256 digests, and byte lengths. It requires an explicit
complete inventory and rejects missing/extra files, case collisions,
noncanonical Windows paths, reparse points, multi-link files, cross-volume
files, and duplicate file object identities. A positive match yields a
deterministic manifest digest independent of enumeration order.

Changed: `tools/hermes_core/app_package_inventory.py` and
`tests/hermes_core/test_ea4e92mf_app_package_inventory.py`.
Focused: 25 passed, 0 failed. Adjacent: 143 passed, 0 failed, one
inherited `app.py` invalid-escape SyntaxWarning.

This module performs no filesystem I/O. The `complete` flag and object
records are caller-supplied and cannot establish trusted enumeration,
protected path/ACL state, retained file handles, package immutability,
interpreter/dependency coverage, or mapped-image bytes. The native
protected enumerator and independently owned launcher remain missing;
these tests must not be reported as production package proof. No app,
issuer, receiver/model, Docker mutation, GPU, ComfyUI, or production
activation occurred.
