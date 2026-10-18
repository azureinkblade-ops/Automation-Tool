# EA-4E.92LU qualified factory source binding

Status: NON-LIVE / STATIC REGRESSION GATE / PRODUCTION HOLD.
Baseline: `72a2aa2a77876cea0da3059216cc9d5091adbe13`.

The 92LT test surface now parses the production receiver registry without
importing it, extracts the two literal executor-factory module names, and
requires both Kilo and OpenCode live-binding files in the static `app.py`
source inventory. An unexpected registry entry or missing local factory
module fails the test instead of silently changing the inventoried set.

Changed: `tests/hermes_core/test_ea4e92lt_app_import_inventory.py` only.
The adjacent 92LT/92LQ gate passed 39 tests, 0 failed. Parsing existing
`app.py` emits its pre-existing invalid-escape `SyntaxWarning` at line
29683; it does not execute the app and did not fail qualification.

This establishes only a source-level registry-to-file relationship. It
does not validate a runtime factory value, third-party dependencies,
installed package identity, a trusted launcher, process/pipe binding, or
the exact mapped-byte invariant. No app/receiver/model was launched and
production remains HOLD.
