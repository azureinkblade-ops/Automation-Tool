# EA-4E.67E Fake Process Tests and Timeout Cleanup

Fake-only harness boundary repaired. Candidate gate: 132 passed / 0 failed /
0 tripwire events. No subprocess or receiver was actually started by that gate.

Previously, three fake-process tests and the stdin test launched cmd, and the
metadata test invoked the real CLI. Tests now inject a fake Popen process or
metadata result, asserting shell=False, DEVNULL stdin, exit status, partial
timeout output, child kill, and a second communicate call to reap the child.
Real CLI metadata evidence remains the separately bounded EA-4E.67B probe.

The genuine timeout test initially failed (106 passed / 1 failed / 0 events):
KiloProcessHandle.wait marked a timed-out process finished without cleanup.
Production fix kills the timed-out child, then performs a bounded communicate
to reap it and collect output before marking finished. A cleanup exception still
propagates through execute's existing kill/error path; no false success is returned.

The 132-test result is against the isolated successor WIP, not a committed
production rollout. Only the timeout cleanup hunk, test harness changes, and
this evidence may enter the remediation checkpoint. Proposed executable pin,
successor historical/cache changes, and credential transport remain uncommitted
pending complete successor-specific regression/reseal qualification.

Dedicated committed-tree checkpoint gate must exercise TestKiloFakeProcess,
TestKiloInjectedMetadataProbe, and TestKiloStdinClosure under the tripwire.
It must not claim the old installed-binary identity remains available.

No app.py changes, durable binding renewal, authorization issuance, live model,
GPU, or ComfyUI work. Original live integration checkout and unrelated WIP intact.
