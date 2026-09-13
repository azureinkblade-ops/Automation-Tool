# EA-4E.89 Committed Bounded Qualification Consolidation

Status: bounded requalification PASS; production readiness NOT established.

Governing synchronized HEAD: ae8b51e70339e66d40dd68e27a6e9c40390587fd.
Tested detached checkout: .worktrees/ea4e88-committed-qualification.
Tested commit: da11a5a6ef145b6fa6922adb212269b1f477e5fd.
The tools/tests diff between those commits is empty; the descendant is evidence-only.
Tracked forward-lane status was empty before this evidence was added.

## Current results

| Envelope | Passed | Process attempts | Prohibited events | Owned survivors |
| --- | ---: | ---: | ---: | ---: |
| EA73 original worker/coordinator | 18 | 14 | 0 | 0 children |
| EA75 frozen pipe matrix | 15 | 15 | 0 | 0 children, 0 readers |
| EA70 controlled worker probes | 2 | 2 | 0 | 0 children |
| EA72 child-policy escape probe | 1 | 1 | 0 | 0 children |
| EA83 Codex metadata/parser | 2 | 3 metadata | limited metadata envelope | metadata only |

Total: 38 passing tests across five separate invocations. All five filesystem
guards reported zero events. EA73 also confirmed two missing-executable
non-launches and fourteen qualified stdin pipe opens. EA70/72 confirmed two/one
qualified pipe opens respectively. Four helper envelopes emitted an assertion
rewrite warning because their filesystem collaborator was imported early; no
test failed. No production or test implementation changed.

These cover the 34 process-boundary nodes that fail under the blanket fake-only
broad gate, plus four additional worker/coordinator assertions. This does NOT
change EA88's raw broad result: 3404 passed, 35 failed, six deselected, 104 passing
subtests. Separate bounded success is not a full-green broad result.

## Reconstructible launch recipes

Run from the detached checkout with the pinned interpreter:
C:/Users/David/Documents/Automation tool/.venv-stage2-v2/Scripts/python.exe.
Every command begins `-m pytest -q -p no:cacheprovider` and includes
`-p tools.ea4e67m_filesystem_guard -p tools.ea4e67n_nonlive_report_host`.
Use a fresh basetemp for every invocation. The remaining arguments are:

```text
-p tools.ea4e73_worker_matrix_guard --ea4e73-original-worker-matrix --basetemp=.pytest-ea4e89-worker-d tests/hermes_core/test_local_worker_runtime_adapter_process.py tests/hermes_core/test_execution_launch_coordinator_real_probe.py --tb=short
-p tools.ea4e75_pipe_matrix_guard --ea4e75-fifteen-pipe-probes --basetemp=.pytest-ea4e89-pipe-a tests/hermes_core/test_opencode_adapter.py::TestOpenCodePipeCapture tests/hermes_core/test_opencode_adapter.py::TestOpenCodePipeOverflow tests/hermes_core/test_opencode_adapter.py::TestOpenCodeReaderFinalization tests/hermes_core/test_opencode_adapter.py::TestOpenCodeRawCapture tests/hermes_core/test_opencode_adapter.py::TestOpenCodeMalformedOutput tests/hermes_core/test_opencode_adapter.py::TestOpenCodeCancellation --tb=short
-p tools.ea4e70_worker_process_guard --ea4e70-two-worker-probes --basetemp=.pytest-ea4e89-probe-a tests/hermes_core/test_ea4e70_worker_process_qualification.py --tb=short
-p tools.ea4e72_child_probe_guard --ea4e72-one-child-probe --basetemp=.pytest-ea4e89-policy-a tests/hermes_core/test_ea4e72_child_policy_probe.py::test_installed_child_policy_denies_escape --tb=short
-p tools.ea4e83_codex_metadata_guard --basetemp=.pytest-ea4e89-metadata-a tests/hermes_core/test_codex_adapter.py::BinaryTests::test_real_requalified_binary_is_present_and_exact tests/hermes_core/test_codex_adapter.py::BinaryTests::test_real_complete_parser_contract_is_accepted_without_model --tb=short
```

Do not compose the blanket fake-only Popen replacement with these independently
bounded process guards. Their own exact-node/argv/hash/budget checks and denial
hooks provide the qualified exception; this is not arbitrary process authority.
The broad fake-only gate continues to use the blanket guard unchanged.

## Failed launch configurations retained

The first worker invocation omitted its explicit envelope flag and was rejected
before tests. The second combined the blanket fake-only and worker guards:
14 failed, four passed; fourteen attempted creations were denied and the worker
guard reported zero actual process attempts, zero owned survivors and zero
filesystem events. Reversing plugin order failed during configuration because
the worker guard then received a deny function instead of the native Popen
class. No process was created by those three failed configurations. No assertion
or guard source was weakened to resolve them. Fresh basetemp evidence remains.

## OpenCode provenance limitation

The historical EA-4E.4 one-shot record reports 944 retained stdout bytes, 96
retained stderr bytes, successful JSONL parsing and normalized text
EA4E4_OPENCODE_LIVE_OK. It does not contain the original JSONL payload in the
reviewed capture/result sections. The expected spool search returned no JSONL:
C:/Users/David/AppData/Local/Hermes/runtime/ea4e/opencode/spool.

This bounded search does not prove the capture is absent from every backup.
The replay test remains unresolved. Do not substitute normalized text or a
synthetic fixture for genuine historical capture, and do not invoke an OpenCode
model to recreate it under non-live continuation authority.

## Next boundary

Review and requalify the six frozen OS crash/durability nodes separately on the
current committed source, retaining evidence and respecting the no-deletion
instruction. Resolve capture through genuine backup/provenance recovery or an
explicitly reviewed test-contract disposition. Real receiver task/model,
production activation, GPU and ComfyUI work remain separately governed and were
not performed. No universal native-syscall isolation is claimed.
