# EA-4E.92RP Pinned Ollama Image Read-Only Inspection

Status: IMAGE PULL AND CONFIGURATION INSPECTION COMPLETE / NATIVE AND MODEL HOLD.
Date: 2026-10-26.
Source baseline before pull: `b5c658dc7e32fda9ff6b9f4c0a01feac204e309a`.

David authorized one pull of the Linux/amd64 image
`ollama/ollama@sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da`
for read-only inspection, with no retry, container start, model request,
GPU use, or production activation. The single `docker pull --platform
linux/amd64` exited 0. Docker reported that exact digest and downloaded the
image. The selected Docker host was
`npipe:////./pipe/dockerDesktopLinuxEngine`.

Read-only `docker image inspect` returned:

- ID and repo digest: `sha256:459985308d740b99071719baec2740a60f5b2b2d9b835c171991ae25690203da`.
- OS/architecture: `linux/amd64`.
- Reported unpacked size: 3,372,424,491 bytes.
- Entrypoint and command: `/bin/ollama serve`.
- Exposed port: `11434/tcp`; no declared volume.
- Image-default `OLLAMA_HOST=0.0.0.0:11434`.

The reviewed 92RN container candidate explicitly overrides `OLLAMA_HOST` to
`127.0.0.1:11434` and requests Docker `--network=none`, but this is source
inspection only. Image history shows a `/bin` copy into `/usr/bin` and an
Ubuntu 24.04 base; it does not prove that the candidate's `/bin/cat` and
`/usr/bin/curl` paths exist. Neither the effective container settings nor
runtime network behavior have been observed. The six pinned model files are
not yet staged in a dedicated read-only mount.

No container was created or started. No model, GPU, receiver, or inter-agent
handoff ran. The image pull authorization is consumed. The next boundary is
a separately scoped, non-model native inspection of tool paths and effective
container containment, or a reviewed replacement for the assumed tools.
Any synthetic model smoke needs a fresh exact authorization after that and
the model mount are qualified. Production remains HOLD.
