# EA-4E.92LT static app import inventory

Status: NON-LIVE / READ-ONLY SOURCE INVENTORY / PRODUCTION HOLD.
Baseline: `5a0fd48804bb9d5a1834dc38a7a4c51d067ea643`.

The new AST scanner reads `app.py` and recursively follows local Python
imports without importing or executing any application module. It hashes
the candidate source files, includes fixed-string runtime imports, reports
unresolved dynamic sites, and accepts only explicit, existing additional
module names. Tests cover recursion, relative imports, cycles, literal and
variable runtime imports, outside-root entry, and a bounded file count.

Against this baseline, the candidate set has 132 local Python files. The
SHA-256 of compact ASCII JSON `[[path,sha256],...]` in sorted path order is
`198c40ed69ea202dc3e806a1061d9143feac8d29285e322c712e51bd59b693d1`.
The qualified registry's Kilo and OpenCode live-binding module names are
already present in that set; explicitly supplying both names produces the
same count and digest. The remaining unresolved site is
`tools/hermes_core/production_executor_binding.py:770`, where the executor
factory path is imported at runtime. The registry currently lists concrete
Kilo and OpenCode factories, but the scanner does not prove every runtime
factory value is constrained to them.

Changed: `tools/ea4e92lt_app_import_inventory.py` and
`tests/hermes_core/test_ea4e92lt_app_import_inventory.py`.
Focused tests: 6 passed, 0 failed. The scanner is an over-approximation of
local Python source, not an approved deployment manifest: it does not attest
the interpreter, third-party wheels/native DLLs, templates, data assets,
environment, optional runtime imports, installed package ACLs, or bytes
actually loaded after process creation. It neither installs nor launches
the app. The independently trusted creator, bounded startup, protected
issuer, real app/pipe binding, and exact mapped-byte proof remain open.
No receiver/model, Docker mutation, GPU, ComfyUI, or production activation
occurred.
