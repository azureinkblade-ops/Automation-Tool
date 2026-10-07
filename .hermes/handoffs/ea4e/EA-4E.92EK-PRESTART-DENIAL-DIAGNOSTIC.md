# EA-4E.92EK prestart network-denial diagnostic

Status: NON-LIVE DIAGNOSTIC PASS / LIVE PROBE HOLD
Baseline: `2ae2734974d8bf9ceb69a0a6dd0213b904db9ef4`
Date: 2026-10-07 (America/Phoenix)

The 92EJ one-shot inert probe stopped before start with the bundled
`container network binding denied` exception. Its created objects were
removed before the exact network subfield could be inspected. This change
does not relax any admission requirement. It separates the same denial
into role-specific reasons for a wrong/missing attachment set, malformed
endpoint record, or endpoint `NetworkID` mismatch. Four new tests cover
the precise reason strings; the complete focused fake-only ladder passes
91/91. No Docker object was created or started for this checkpoint.

The current cause of 92EJ remains unknown. Do not infer that Docker omits
the prestart network ID merely because that is one possible denial path.
A next attempt should be a separately authorized **diagnostic-only**
create-and-inspect run: the exact pinned image, one fresh internal network,
two never-started helper containers, a bounded sanitized denial record,
and exact-ID cleanup. It should stop after prestart inspection regardless
of outcome. The earlier one-shot approval is consumed and cannot be used
for that run. Only after a real snapshot identifies the discrepancy should
the frozen admission contract be revised and requalified, if warranted.

`FIELD_SPECIFIC_DIAGNOSTIC=PASS`
`FOCUSED_TESTS=91_PASS`
`OLD_ONE_SHOT_APPROVAL_CONSUMED=YES`
`NEW_DOCKER_PROBE_EXECUTED=NO`
`PEER_QUALIFIED=NO`
`PRODUCTION_READY=NO`
