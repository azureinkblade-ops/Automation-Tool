# EA-4E.92UG large-memory non-model candidate

Date: 2026-10-27
Status: SOURCE-ONLY CANDIDATE / NATIVE HOLD

The 92UD small non-model Bash control passed on this host with Docker
`json-file` logging. This candidate retains that exact non-model envelope
except for memory and swap limits, each raised from 256 MiB to 8 GiB. It
uses its own exact-owner prefix. The pinned image, `--network none`, zero
mounts and ports, no GPU assignment, read-only root, explicit
`NVIDIA_VISIBLE_DEVICES=void`, one CPU, 16 PIDs, 16 MiB `/tmp` tmpfs,
one-file 16 KiB requested `json-file` logging, disabled restart, and
`/bin/sh -c 'sleep 45'` are unchanged. It checks only Bash, cat, loopback,
and an expected-refused connection to `127.0.0.1:1`.

The effective memory and swap limits are checked before start. The
existing exact-owner cleanup and absence confirmation remain. Requested
Docker log options are not a hard disk/retention bound. The 8 GiB memory
limit is materially larger and may affect host resources if started; the
prior read-only daemon report was about 16.6 GB total, not a guarantee
of available memory. Focused strict non-live fake tests passed (103/103),
including success, pre-start memory mismatch, failed-start cleanup, and
unreviewed-mode denial. Fake tests do not establish native behavior.

A new independent read-only review of pinned committed source and a
separate exact one-shot native authorization are required before any run.
No Docker container, Ollama server, model, GPU, receiver, or agent handoff
ran for this candidate. Production remains HOLD.
