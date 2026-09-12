# EA-4E.67S Sequential Cross-Receiver Fixtures

Baseline: 1af712bd0f0f39090ae8c2c33794830ab8c836a2.
Scope: EA-4E.36 entrypoint test module and this evidence only.
No production, guard, or successor WIP changes.

Isolated original cross-receiver test reproduced BINDING_LIMIT_EXCEEDED
before receiver mutation validation. The fixture bound two receivers at once.
An intermediate single-binding setup returned MISSING_BINDING_ENABLEMENT
(22 passed / 2 failed), proving target binding validation precedes mismatch.
Neither historical failure was hidden by altering expected production reasons.

The final two direction tests explicitly assert second simultaneous binding
rejection, active count one, and no target binding. They retain the source
handle, tear it down, then create the target binding with active count one.
The source receiver's issue request is submitted against the target receiver;
POST_ACTIVATION_RECEIVER_MUTATION is still required. Both fake executor call
counts must remain zero. No forged binding lookup or weakened one-binding
limit is used. Sequential binding transitions represent test setup only.

Candidate gate: complete EA-4E.36 module plus filesystem isolation, report
host, and process guard test modules: 52 passed / 0 failed / zero process
and filesystem events. Fresh explicit basetemp; unchanged guards.

Independent gate uses python -m pytest -q -p no:cacheprovider
-p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard
-p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-s-export-a
and the four modules above with --tb=short. Verify staged-only and actual
committed exports. This is not complete successor qualification.

Other EA-4E.37-41 fixture failures, real-process tests, and missing binary
or replay fixtures remain open. The EA-4E.67Q broad HOLD remains historical.
No real receiver/model invocation, authorization ceremony, GPU/ComfyUI,
deployment or server restart occurred. No existing files were deleted.
