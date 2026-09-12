# EA-4E.67K Frozen Helper and Abrupt Crash Qualification

Governing parent: 37e3529297ff2efe7ee2ca6f70c46fbbab5b028f.
This is a bounded qualification-harness slice, not successor rollout/deployment.
EA-4E.67J's results and evidence limits remain historical.

## Frozen process envelope

- Interpreter: C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe
- Interpreter SHA-256: 0a864203aee170314ece97beaad6e50e226e76f0a3d73380a93ec472ed74f040
- Helper: tests/hermes_core/fixtures/durable_auth_process_helper.py
- Helper SHA-256: d2aa771a24adacd7fb3f3b1c2c8b3eaa6b8800dfff27315fd7010d02d7265ab1
- Six exact test nodes; maximum fourteen launches; modes claim,
  precommit-crash and postcommit-crash only.
- Isolated temporary database/anchor paths, explicit pipe capture, DEVNULL stdin,
  credential-free inherited environment allowlist, parent network/shell denials,
  child audit-hook network/nested-process denials, and session-end cleanup.
- Exact LF helper bytes preserved by a single-path .gitattributes text eol=lf rule.

No universal OS containment is claimed. Path/hash checks are qualification
tripwires, not protection against a hostile concurrent filesystem writer.
Interpreter identity covers the executable, not the complete Python installation.

## Stronger evidence

New abrupt postcommit test calls os._exit(23) from the existing store hook after
database commit and before anchor publication. Exit 23, no successful grant
output, unchanged anchor, and consumed database row are asserted. A subsequent
claim raises the integrity error, rather than granting or silently repairing.
Production store code is unchanged.

New four-process test requires one ALLOW, three DENY, all return codes zero,
empty stderr, and exactly one durable consumption. ERROR is not accepted.

Guard negatives cover executable, mode, state root, shell, pipe capture, process
budget, helper tamper, interpreter tamper, network, startup node selection,
startup identities, missing basetemp, and unfinished-child kill/reap failure.

## Candidate results

- Six exact process nodes: 6 passed, 14 helper launches, zero denials.
- Strict fake guard denial/cleanup suite: 14 passed, zero outer tripwire events.
- Combined restart/durability/concurrency/guard/successor candidate ladder:
  256 passed, 4 explicitly excluded real-process nodes, zero tripwire events.
- All runs used no cacheprovider and fresh explicit basetemp directories.

Candidate ladder includes unrelated uncommitted successor WIP; it is not
committed-tree evidence. Clean export qualification is required for this slice.
No full Hermes Core green claim is made.

## Clean precommit export

Index tree 82e14b8286a770385bffc7890a8eef0c56ee4e2b was archived into
ea4e67k-index-20260912a using tracked tools/tests and the byte policy only.
The process guard accepted the exact frozen helper bytes from that export.
Six real-process nodes passed with 14 launches and zero denials. Complete
31/32/33/33A/H/J fake-only ladder passed 216 tests, excluding only the four
separately qualified historical process nodes, with zero tripwire events.
No untracked dependency or successor WIP was needed by these exported gates.
Only this evidence section changes after that successful index export.

Precommit diff checking exposed CRLF bytes in the initial -text helper policy.
The helper was mechanically normalized to LF and the policy narrowed to
text eol=lf, producing the final helper hash above. The initial export results
remain historical; a fresh final index export must requalify the new exact bytes.

Final LF-corrected index tree f85766445dc2abdc4e3fc48f5316443f268bfc27
was exported into ea4e67k-index-20260912b. Gates again passed: 6 real-process
tests, 14 launches, 0 denials; 216 fake-only tests, 4 separately qualified
historical process tests deselected, 0 tripwire events. git diff --cached --check
passed. No production/test changes followed that final export qualification.

## Exact checkpoint closure

1. .gitattributes
2. tests/hermes_core/fixtures/durable_auth_process_helper.py
3. tools/ea4e67j_durability_process_guard.py
4. tests/hermes_core/test_ea4e67j_process_guard.py
5. tests/hermes_core/test_ea4e67k_process_durability.py
6. .hermes/handoffs/ea4e/EA-4E.67J-BOUNDED-PYTHON-DURABILITY-QUALIFICATION.md
7. This EA-4E.67K evidence file

Successor production/test WIP, earlier HOLD artifacts, generated test folders,
and original integration worktree remain excluded. No authorization issuance,
activation, receiver/model task, GPU, ComfyUI or server restart is authorized by
this checkpoint. Next independent work is successor reproducible closure review.
