# EA-4E.67P Temporary Profile Fixture Isolation

Baseline: c85e829f413c9b464d2e5c57cdee94b757738eaa.

Scope: two test modules only, plus this evidence. No production or guard changes.

The two Kilo profile creation/hash tests temporarily patch AGENT_DIR and
AGENT_FILE to pytest-owned paths. Pytest restores both after each test.
Creation verifies exact profile content; hashing verifies content changes
change the hash. The read-only deployed-path ownership assertion remains.
OpenCode safe_cwd now returns tmp_path rather than creating repository
.pytest_iso directories. No files were deleted.

Candidate qualification using the unchanged process/filesystem guards and
reporting plugin, explicit fresh basetemp, and JUnit reporting:
- Kilo/OpenCode selection: agent_profile or config_rejects or resolve_rejects_wrong.
  20 passed, 169 deselected; both tripwire counts zero.
- Filesystem isolation, reporting, process guard, and OpenCode 25A forensic suites:
  44 passed; both tripwire counts zero.
- git diff --check: passed (line-ending notices only).

These results repair the two live-profile mutation attempts and seven
out-of-basetemp fixture errors documented in EA-4E.67O. They do not qualify
the complete successor chain or classify all remaining broad failures.
The previous broad result remains 3208 passed / 75 failed / 7 errors,
104 subtests passed, 6 deselected. A fresh broad rerun is still required.

No receiver execution, model invocation, authorization issuance, GPU work,
ComfyUI calls, deployment, or server restart was performed.
Successor WIP is excluded from this checkpoint.

## Independent staged-source result: HOLD

Staged tree 368b8d16c8d65f0088e4e84d84ad278cca566661 was exported
with tools, tests, and docs/architecture, without successor WIP.
The same 20-test selection returned 19 passed / 1 failed / 169 deselected;
both tripwire counts remained zero. The failing node was
TestKiloBinaryVerification.test_resolve_rejects_wrong_version_via_fake_probe,
which resolves the committed, missing Kilo 7.5.16 executable before using
its fake version probe. Candidate success for this node depended on the
excluded successor adapter WIP. It is not proof of fixture closure.

COMMIT_CREATED=NO
PUSH_PERFORMED=NO
CHECKPOINT=HOLD_PENDING_INDEPENDENT_SCOPE_QUALIFICATION

Next: explicitly qualify the repaired profile nodes and seven OpenCode
fixture nodes on committed-source exports; classify the old-binary node
separately without weakening verification or promoting successor WIP.

## Exact-scope continuation: PASS

On the independent staged export, run the unchanged guards/report plugin
with --basetemp=.pytest-p-exact-b and JUnit under that directory:
- KiloSecurityFocused: profile_exists, profile_hash_is_64_hex,
  profile_path_is_hermes_owned (exact full names prefixed test_agent_).
- OpenCodeTrustedConfig class (7 tests), plus BinaryVerification wrong_sha
  and wrong_version_via_fake_probe.
- test_ea4e67m_filesystem_isolation.py, test_ea4e67n_nonlive_report_host.py,
  test_ea4e67j_process_guard.py, and OpenCode 25A forensic suite.

Result: 56 passed, zero process events, zero filesystem events.
This explicitly includes the repaired nodes and neighboring safety tests;
it is not a replacement result for the earlier 20-test selection.
The missing committed old-binary dependency remains unresolved and visible.
No production semantics, binary identity, guard, or successor WIP changed.
Fixture-only checkpoint is now qualified for independent final verification.
