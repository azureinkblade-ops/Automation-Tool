# EA-4E.92UJ json-file model-mount non-model candidate

Date: 2026-10-27 (America/Phoenix)
Status: SOURCE-ONLY CANDIDATE; PRODUCTION HOLD

## Evidence and boundary

- 92UI proved a one-shot non-model shell start at an 8 GiB memory/swap limit with Docker `json-file` logging, zero mounts, and exact-owner cleanup. It did not prove model capacity.
- This candidate keeps the existing 92TJ non-model model-mount envelope: pinned image, validated six-file qwen3:14b stage mounted read-only at `/models`, 8 GiB memory/swap, four CPUs, 64 PIDs, 2 GiB `/tmp`, `--network none`, no published ports or GPU assignment, read-only root, dropped capabilities, no-new-privileges, restart disabled, and `/bin/bash -c 'sleep 60'`.
- The candidate changes only the requested Docker log driver from `local` to `json-file` with one-file `max-size=16k` options. These options are not a hard disk or retention bound. It remains a non-model startup/interface check: no Ollama server, HTTP request, inference, receiver, or agent handoff.
- A dedicated plan flag rejects unreviewed combinations and verifies the effective log driver before start. Exact-owner cleanup and absence confirmation remain in the shared runner.
- Focused strict non-live fake tests passed: 113/113 across the shared container runner and adjacent Bash transport tests. Fake tests do not establish native behavior.
- No Docker/container, model, GPU, receiver, handoff, or production activation was performed for this checkpoint.

## Next gates

1. Independently review the committed source and tests, especially plan gating, effective containment, failure cleanup, and the no-inference path.
2. Only after a passing review, seek a new exact one-shot authorization for the pinned native non-model mount check. Prior approvals are consumed and do not carry forward.
3. If native evidence passes with exact cleanup, assess the remaining private-model smoke and inter-agent handoff gates separately. Production remains HOLD.
