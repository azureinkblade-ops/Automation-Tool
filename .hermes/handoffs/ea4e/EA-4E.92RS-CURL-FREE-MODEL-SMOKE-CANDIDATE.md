# EA-4E.92RS Curl-Free Model Smoke Candidate

Status: NON-LIVE CODE CANDIDATE / INDEPENDENT REVIEW AND MODEL RUN HOLD.
Date: 2026-10-26.
Parent native evidence: `ae8c9a2` (92RQ).

The 92RQ native probe found `/usr/bin/curl` absent in the pinned Ollama
image. This successor changes only the local model request path in
`tools/ea4e92rm_container_smoke.py`: after the existing containment and
loopback-interface checks, it makes one noninteractive `/bin/ollama run`
request with `--format=json`, `--think=false`, `--keepalive=0`, and the
exact `qwen3:14b` model name. It accepts only the complete JSON object
`{"marker":"EA4E_LOCAL_SMOKE_OK"}`. No curl or secondary version probe is
required. The fake boundary tests cover one invocation, pre-inference
denial, wrong marker, extra response field, model-file drift, and exact
owned-container stop. They passed 14/14 under the strict non-live guard.

Pinned upstream source at Ollama v0.40.11 documents `run MODEL [PROMPT]`,
these flags, and noninteractive behavior:
`https://github.com/ollama/ollama/blob/v0.40.11/cmd/cmd.go`.
Its `RunHandler` calls `showOrPullModel`, which can attempt a pull or suggest
a cloud variant if the requested model is absent. The candidate's
`--network=none` and read-only six-file model mount prevent network egress
and model-store writes, but the fallback means a missing model must fail
closed; it is not evidence of a successful local run. An independent review
must assess this changed request path and effective call accounting before
any one-shot native model authorization.

No changed launcher, model, GPU, receiver, or agent handoff was run. The
six-file dedicated model mount is not staged. The previous host-executable
smoke approval and the 92RQ non-model probe approval are consumed or do not
cover this successor. Production remains HOLD.
