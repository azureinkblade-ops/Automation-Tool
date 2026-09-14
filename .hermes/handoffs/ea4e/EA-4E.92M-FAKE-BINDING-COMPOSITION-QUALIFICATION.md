# EA-4E.92M Fake Binding Composition Qualification

Baseline: b866cc589077f2c339e59f3691008d209fd7004f.
Scope: test-owned composition of EA92J supplied-byte verification and existing
EA92C durable qualification gate. No production composition or acquisition API.
Status: FOCUSED/STAGED QUALIFIED; FINAL COMMITTED GIT-BACKED GATE REQUIRED.

## Files and Ownership

Only tests/hermes_core/test_ea4e92m_fake_binding_composition.py and this evidence
document belong to the checkpoint. New harness helpers are test-owned, not
production or authority owners. No exports, registry or core code changed.
The fixture reads the committed EA92I design JSON; that document is an explicit
dependency. Runtime/config/policy bytes and request body are synthetic fixtures.

The verifier precedes gate reservation. A separate expected binding ID is checked
against supplied material and the fake gate scope. Runtime/config/four policy
hash mismatches, missing/extra policy, expected-ID and scope-ID mismatch all stop
without forwarding or consuming. Tampered body/model/endpoint, expiry and fixture
cancellation/revocation deny at the gate. Verified composition forwards exactly
once; reopening the durable temporary store does not refund or permit replay.
The verified canonical snapshot remains immutable after caller mutations.

## Exact Qualification

Interpreter: C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe.
All pytest commands use -q -p no:cacheprovider and plugins
tools.ea4e67_fake_only_guard, tools.ea4e67m_filesystem_guard,
tools.ea4e67n_nonlive_report_host, plus fresh retained --basetemp.

Focused files: test_ea4e92m_fake_binding_composition.py (18),
test_ea4e92j_provider_binding.py (117), test_ea4e92c_provider_call_control.py (20).
Working run: 155 passed, 0 failed; both tripwire event counts zero.
Initial run: 154 passed, 1 failed because the test helper's body positional
argument collided with the body-tamper keyword. Renamed captured_body; full
rerun passed. No gate production semantics changed.

Staged source tree: 27b8c0b08952c7e643cd5b9a1b7d3364b8172568.
Retained .ea4e92m-index-a export includes tools/tests/design dependencies.
Focused ladder adds test_ea4e92d_fake_provider_accounting.py and
test_ea4e92f_offline_provider_http.py: 187 passed, 0 failed, zero tripwire events.

Full tests/hermes_core/ gate uses --tb=no and the established six OS-node
exclusions: test_multi_process_claim_tested, test_os_process_precommit_crash_tested,
test_os_process_postcommit_crash_tested,
test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent,
test_abrupt_postcommit_crash_keeps_consumption_and_fails_closed,
test_simultaneous_claims_have_one_winner_and_three_clean_denials.
No inherited failure is marked xfail or hidden by these exclusions.

First partial export full-gate attempt: 11 collection errors, root app
dependencies omitted. Corrected by full tracked-tree export, without test edits.
.ea4e92m-index-full-a full gate: 3594 passed, 36 raw failed, 6 deselected,
104 subtests passed, 1 inherited warning; exit 1. 34 denied subprocess attempts,
zero filesystem tripwire events. No actual receiver/model process ran.
Report: .pytest-ea4e92m-broad-b/result.xml under that retained export.

Exact failure identity comparison with EA92J: all 35 previous failures remain;
one added RuntimeNamespaceTests.test_live_harness_head_is_valid_source_binding.
Isolated export reproduction proves FileNotFoundError on archive's .git/HEAD.
Same test in Git-backed lane passes 1/1, zero tripwire events. This is export
environment dependence, not an EA92M production regression. Final acceptance
requires a full clean committed Git-backed rerun with the test included.

## Limits and Next Boundary

These tests qualify only synthetic composition order and durable fixture replay.
No real SDK request was captured; JSON body is constructed by this test harness.
No trusted filesystem acquisition/owner, package provenance, OS egress containment,
CPU policy, actual durable cancellation race or OpenCode cleanup owner is proven.
Fixture cancellation booleans are not real durable cancellation authority.
No host/config mutation, listener, production authorization issuance, receiver/
provider/model invocation, GPU/ComfyUI, downloads or file deletion.

Real target artifact freeze and production readiness remain HOLD. Do not roll
shared IDs or register a fixture digest. Next design/qualification work must
resolve trusted acquisition and effective SDK compatibility without inventing
policy bytes or treating supplied identity agreement as enforcement.
