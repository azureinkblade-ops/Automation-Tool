# EA-4E.92S Windows Resource Layer - Partial Implementation

Date: 2026-09-14
Baseline: 2b37424378a8c78f57d5c99ddafc84af2b0cb4e2
Status: IMPLEMENTED / FAKE TARGETED PASS / UNCOMMITTED
Native enforcement: NOT QUALIFIED

## Scope

tools/ea4e92s_windows_job.py: explicit lazy Windows native bindings and job
preparation, no process launcher. tests/hermes_core/test_ea4e92s_windows_job.py:
fake API and host ABI fixtures. This evidence is the third candidate file.
No existing production workflow or image/Studio Bible pipeline modified.

The implementation checks one-process, 256 MiB process-memory and kill-on-close
limits by readback before returning a job handle. Preparation failure closes only
that owned handle. Cleanup uncertainty raises UnknownJobCleanup; caller must not
retry automatically. Caller owns closure on success. No default backend is loaded
at import or by prepare_job. Tests never construct WindowsJobApi.

Job controls do not enforce network/filesystem isolation, wall-clock deadlines,
bounded stream capture, parser identity or creation-time job membership. They
must not be used to claim a safe Node sandbox. No actual job API invoked.

## Design Correction

The prior draft's create-suspended/assign-afterwards pattern contains a broker
crash/orphan window. Future creation must use a preconfigured owned job through
PROC_THREAD_ATTRIBUTE_JOB_LIST, alongside reviewed security attributes, and
verify membership before resume. No assignment/creation API implemented here.
Source: [Microsoft creation-time job guidance](https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812).
Resource semantics were checked against [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [Basic Limit Information](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information).

## Targeted Verification

Pinned interpreter:
C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe

```text
python -m pytest -q -p no:cacheprovider -p tools.ea4e67_fake_only_guard -p tools.ea4e67m_filesystem_guard -p tools.ea4e67n_nonlive_report_host --basetemp=.pytest-ea4e92s-job-a tests/hermes_core/test_ea4e92s_windows_job.py tests/hermes_core/test_ea4e92s_containment_lifecycle.py tests/hermes_core/test_ea4e92s_parser_source.py tests/hermes_core/test_ea4e92p_static_binary_inspection.py
```

16 fake Job fixtures + 53 predecessors = 69 passed / 0 failed, 0.28s.
Both process/network and filesystem tripwire events: 0. No WinDLL construction.
64-bit structure/layout tests are not actual Windows syscall qualification.

Full/staged/committed regression for this new slice NOT RUN. Prior raw 35 failures
remain historical, not normalized. No staging, commit, push, process/SDK/receiver/
model/GPU execution, security mutation or deletion. Native containment remains
OPEN; next slice is fake-tested creation-time job/security-attribute composition.

## Combined Review and Working-Tree Regression

Creation composition now exists as a separately evidenced fake-only helper.
Review reproduced a job cleanup recovery gap: UnknownJobCleanup did not expose
the owned handle/API. Four enhanced fake assertions failed before the minimal
exception-context correction, then all 93 combined bounded tests passed with
zero tripwire events. UnknownJobCleanup now retains api and handle for caller
reconciliation; no automatic retry or native cleanup qualification is implied.

Combined full Hermes Core fake-only gate: 3688 passed / 35 raw failed /
6 unchanged OS-test deselections / 104 subtests passed, exit 1, 117.29s.
Exact failed-node comparison with committed 2b374243 evidence: 35 unchanged,
added 0 / resolved 0. 34 denied Popen attempts, filesystem tripwire 0.
Report .pytest-ea4e92s-native-full-a/result.xml SHA256:
9fad2e803dd62ae673db47a2412b2cfbb87f6a75e1b1081a5ceec220e4bd61a6
Same pinned interpreter/guard plugins, full tests/hermes_core, --tb=no and the
same six OS exclusions used by the predecessor committed gate.

Classification: combined working-tree no-new-regressions PASS; raw gate NOT GREEN.
Six reviewed candidates across job/composition slices may enter the narrow
staged-export bounded gate. Record exact final tree/result in the vault without
recursively changing evidence. Full staged/committed gates not yet run.
No native API/process/SDK execution or security settings changed; no commit/push.
