# EA-4E.92TI non-model mount/start exit-128 HOLD

Date: 2026-10-27

David authorized exactly one native run of the independently reviewed 92TG
non-model mount/start probe. Source was at `d6ce968c819f4174d024e54821f687943254a731`;
the reviewed runtime was unchanged from `abd4fe01f868a82c4cbfda4dd2cda3e8a081e8f4`.
Before the run, the entrypoint, runner, and Docker CLI SHA-256 hashes matched
the authorization, the six-file qwen3:14b stage validated, no old `ea4e92tg-`
container existed, and the pinned image ID matched.

The single run failed at `docker container start`. Fixed-category output was
`exit_code=128 oom=false startup_category=unclassified`. The sleeping Bash
command did not start; loopback inspection, HTTP, Ollama server, model
inference, receiver, and agent handoff did not run. No GPU was assigned and
there was no published port. The probe's exact-owner cleanup completed, and
a separate read-only Docker query returned no `ea4e92tg-` container. No retry
occurred. The one-run authorization is consumed.

This reproduces the start failure with a non-model Bash command while keeping
the model-stage read-only mount and 20 GiB/four CPU/64 PID envelope. It narrows
the failure away from Ollama server startup, but does not distinguish the mount,
resource limits, daemon policy, or other create/start factors. The reported
daemon memory is below the requested container memory limit, but the cause
remains unproven. Any further native experiment needs a new bounded design,
review, and exact one-shot authorization. Production remains HOLD.
