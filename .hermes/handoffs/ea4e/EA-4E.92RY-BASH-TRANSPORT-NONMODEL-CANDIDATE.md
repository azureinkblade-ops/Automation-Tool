# EA-4E.92RY Bash Transport Non-Model Candidate

Status: NON-LIVE CANDIDATE / INDEPENDENT REVIEW AND NATIVE APPROVAL HOLD.
Date: 2026-10-26.
Predecessor: `09c5df8` (92RX source-only review).

The prior pinned Ollama image probe found `/usr/bin/curl` absent. The
reviewed smoke candidate instead uses Bash `/dev/tcp` inside a `--network
none` container, but this capability has not been observed natively. This
new one-shot, non-model probe reuses the earlier exact-owned-container
boundary with a separate 92RY name and owner label. It checks `/bin/bash`
and `/bin/cat`, attempts only `127.0.0.1:1` from inside the container, and
requires Bash's `Connection refused` result plus only the `lo` interface.
The probe mounts no model, starts no Ollama server, assigns no GPU, and does
not issue a model request. The Docker inspection parser now rejects
duplicate JSON keys.

The focused strict non-live suite passed 30/30 fake tests across the probe
and smoke candidate. This does not establish that the pinned image has Bash
network redirection or that the Docker daemon will honor the envelope. A
fresh independent read-only source review is required before requesting a
new, exact, one-shot native authorization. The 92RQ authorization was
consumed and cannot be reused. No native action occurred for this candidate.
Production remains HOLD.
