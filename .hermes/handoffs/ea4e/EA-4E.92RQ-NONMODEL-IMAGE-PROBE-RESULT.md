# EA-4E.92RQ Non-Model Image Probe Result

Status: NATIVE NON-MODEL PROBE COMPLETE / MODEL SMOKE HOLD.
Date: 2026-10-26.
Source baseline: `cc5cec277b7c3267710873166ca0229bb2308a4a`.

David authorized exactly one bounded native probe of pinned image
`ollama/ollama@sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da`.
The one-shot shell-only probe was run through
`tools/ea4e92rq_nonmodel_probe.py`; the pinned Docker CLI hash matched
`c11b843b727ea76e6c63b393bccb73d957b6fcc12ba871c8265699e3a12e933c`.
The probe verified the effective image ID, Linux/amd64 platform, and
created-container restrictions before start: network none, no published
ports, no GPU device requests, no model mount, read-only root, dropped
capabilities, no-new-privileges, memory/CPU/PID limits, and restart disabled.
The entrypoint was `/bin/sh`, with only a bounded sleep command; Ollama was
not started. The process returned within the two-minute envelope.

The single native observation was:

- `/bin/cat`: executable.
- `/usr/bin/curl`: absent or not executable.
- Interfaces in `/proc/net/dev`: `lo` only.

The probe's exact-ID-and-owner cleanup returned successfully. A separate
read-only `docker ps -a` query by its owner label returned no container.
The authorization is consumed; there was no retry. No model file was
mounted, and no model, GPU, receiver, or inter-agent handoff ran.

The independently reviewed 92RN model-smoke candidate assumes
`/usr/bin/curl` for its localhost version and generate calls. It cannot be
run as-is against this pinned image. Before any synthetic model smoke,
replace that HTTP transport with a reviewed image-compatible mechanism,
requalify the changed launcher, and stage only the six pinned model files
into a dedicated read-only mount. A fresh exact model-run authorization is
still required. Production remains HOLD.
