# EA-4E.92UI large-memory non-model pass

Date: 2026-10-27
Status: ONE AUTHORIZED NATIVE NON-MODEL RUN PASSED / PRODUCTION HOLD

The exactly one authorized 92UG 8 GiB memory/swap comparison used source
commit `e7b827b1e4d93d71dc3e1205bae82bf59677b3fa`, with runtime
unchanged from independently reviewed commit
`f89a102315dd74082e8f76505ec6c1466402059a`. Entrypoint, runner,
imported Docker client, and Docker CLI SHA-256 pins were checked before
invocation. The probe passed with the pinned image, only loopback visible,
and `/bin/bash` and `/bin/cat` executable. The expected-refused Bash
connection to `127.0.0.1:1` was enforced. The exact-owned container was
removed and absence confirmed by the probe; a separate read-only Docker
query found zero residual 92UG containers.

Relative to the passing small `json-file` control, this proves that a
non-model shell container with an 8 GiB memory/swap limit can start and
complete the bounded checks on this host. It does not prove that 8 GiB
was actually available to a model, nor qualify the larger CPU/PID/tmpfs
settings, model mount, Ollama server, inference, receiver, or handoff.
Requested log options are not a hard disk/retention bound before removal.

The one-run authorization is consumed; there was no retry. No model,
GPU, receiver, agent handoff, cloud call, or production activation ran.
Any further native step requires separate reviewed source and exact
authorization. Production remains HOLD.
