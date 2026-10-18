# EA-4E.92LY bounded text-question command

Status: NON-LIVE / PURE COMMAND PLAN / PRODUCTION HOLD.
Baseline: `57ca6cfd1a52753ccc265054c1d3376036b4d042`.

This checkpoint adds a pure Kilo/OpenCode command plan for an accepted
`agent_text` task using `hermes.agent_text_result/v1`. The task must carry
one nonblank question of at most 512 UTF-8 bytes, no instructions or input
manifest, no read/write paths or tools, denied network, at most 60 seconds,
no redelegation, and the exact receipt-evidence contract. The lease and
bridge must agree with the same receiver, attempt, receipt, launch, and
start result. OpenCode still requires an explicit trusted config and
qualified runtime binding. The Kilo/OpenCode builders and existing durable
intent store receive a deterministic argv hash. The original ping command
and result path are unchanged.

Focused command and ping-command tests: 13 passed, 0 failed. The adjacent
text-return, three-agent handoff, terminal-capture, and result-store ladder
passed 154 tests plus 6 subtests, 0 failed.

Question text is task data, not authority. The command prompt requests
the bounded JSON text-result schema but cannot prove a real model will
obey it. The terminal-capture and 92LW/LX result-return checks remain
separate. The plan does not authorize execution, create a process, contact
a model, mutate Docker, or activate production. The strict Windows 92AT
route remains REJECT/HOLD and the separate local-Docker route remains
unqualified.
