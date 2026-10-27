# EA-4E.92TY current-host non-model control PASS

Date: 2026-10-27
Status: NATIVE NON-MODEL CONTROL PASS / MODEL GATE HOLD

David authorized exactly one current-host non-model Bash control at source
`d689fc6821afe06729b9fff093298349eae448af`, with runtime unchanged
from the independently reviewed `2156dd2c76fcdfbcf10f0902e806d59fb52fcf8d`.
Before the run, the worktree was clean and the entrypoint, shell runner,
imported Docker client, and Docker CLI SHA-256 hashes matched the exact
authorization. The same pinned Ollama Linux/amd64 image was used, but no
Ollama server or model was started.

The single run exited zero. It reported only the `lo` interface and the
availability of `/bin/bash` and `/bin/cat`; the probe also required a
refused localhost Bash connection to succeed. Its one exact-owned container
used the previously successful 92SA envelope: network `none`, no model
mount, published port, or GPU assignment, read-only root, 256 MiB memory
and swap, one CPU, 16 PIDs, 16 MiB `/tmp` tmpfs, Docker logging disabled,
and restart disabled. The runner confirmed exact-owner removal, and a
separate read-only Docker query returned zero `ea4e92ry-` containers. No
retry occurred. The one-run authorization is consumed.

This requalifies the small non-model control on the current host. It makes
a universal Docker engine outage less likely but does not identify why the
larger 92TV envelope failed at start with exit 128. Multiple configuration
variables differ, so any next native comparison must change only a reviewed
bounded variable from this control and obtain a new exact authorization.
No model, receiver, agent handoff, GPU, cloud, or production activation ran.
Production remains HOLD.
