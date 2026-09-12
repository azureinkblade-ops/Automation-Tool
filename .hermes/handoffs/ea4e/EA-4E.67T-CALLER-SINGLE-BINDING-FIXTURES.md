# EA-4E.67T Caller Single-Binding Fixtures

Baseline: a3688fc05d32ef459b166d5dc632bef6e8741542.
Scope: EA-4E.37 test module and this evidence only.

Three caller mutation tests unnecessarily bound both registered fake receivers.
They now bind only the authorization's originating receiver. All three assert
active binding count one and no target binding. They still require
CALLER_TO_ENTRYPOINT_RECEIVER_MUTATION, entrypoint_called False, and zero calls
to both registered fake executors. Unlike the lower entrypoint (67S), the
caller rejects the mismatch before entering the entrypoint, so a sequential
target binding is unnecessary. No forged handle or binding lookup is used.

Candidate verification under unchanged process/filesystem/reporting guards:
EA-4E.37, EA-4E.36, filesystem isolation, report host, process guard modules:
72 passed, zero process events, zero filesystem events.

Reproducible gate: python -m pytest -q -p no:cacheprovider
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e67t-gate-a
with the five modules above and --tb=short. Verify staged-only and actual
committed exports before checkpoint push. No production or guard edits.

The broader successor HOLD remains. EA-4E.38-41 fixtures, genuine process
qualification, and missing binary/replay dependencies are separate open work.
No real receiver/model, authorization ceremony, GPU/ComfyUI, deployment,
server restart or file deletion occurred. Successor WIP remains excluded.
