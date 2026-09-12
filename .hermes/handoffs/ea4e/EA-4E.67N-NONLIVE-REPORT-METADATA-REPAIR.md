# EA-4E.67N Non-Live Report Metadata Repair

Parent: 8f1afaf18620008417011125e93cc115600d892e.
Scope: reporting-only qualification harness. Successor WIP excluded.

## Historical diagnostics

The first guarded broad run lost its process handle across a user continuation;
its XML contained only a declaration. No final counts may be inferred.
The fresh b run reached 100% but pytest JUnit sessionfinish called platform.node,
which on this Windows runtime attempted a subprocess through platform.win32_ver.
The unchanged process guard blocked the attempt. Exit 1, incomplete XML, no
authoritative final totals. Its retained log and both XML stubs remain intact.
These runs are not full qualification evidence or a replacement for EA67L totals.

## Repair

An explicit pytest reporting plugin wraps sessionfinish, substitutes
NONLIVE_QUALIFICATION_NOT_OS_HOSTNAME for platform.node only during reporting,
and restores the original function even if reporting raises. It does not
represent that label as the actual machine hostname. No process/network guard
exception, new subprocess permission, production capability or test-result
substitution is introduced. Test execution occurs before this wrapper.

Two regressions prove normal restoration and restoration on reporting failure.
Bounded reporting+filesystem+25A gate: 30 passed, process/filesystem events zero.
Parsed completed XML: tests 30, failures 0, errors 0, synthetic hostname exactly
as documented. Expanded 31/32/33/33A/H/J/M/N/25A ladder: 246 passed, four
historical process tests separately qualified and excluded, both guard counts 0.
No full Hermes Core green claim is made.

## Three-file checkpoint

1. tools/ea4e67n_nonlive_report_host.py
2. tests/hermes_core/test_ea4e67n_nonlive_report_host.py
3. This evidence file

No runtime deployment, receiver/model invocation, authorization issuance,
activation, GPU or ComfyUI work occurred. All source and report artifacts stay
separate from the original integration lane. Clean exported-source and committed
tree gates are required before push. Remaining broad failures still need final
structured diagnostics and case-by-case baseline classification.

Clean staged export tree 9aec5a5e5a106faa9abda8441a26afe289fc4ba0 into
ea4e67n-index-20260912a repeated 246 passed, four separately qualified process
nodes excluded, both guard counts zero. Completed XML parsed tests=246,
failures=0, errors=0 and the explicit synthetic report host. No successor WIP
or untracked source dependency needed; staged whitespace check passed.
