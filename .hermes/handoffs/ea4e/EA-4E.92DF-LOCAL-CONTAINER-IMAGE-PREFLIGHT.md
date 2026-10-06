# EA-4E.92DF local-container image preflight

Status: SOURCE-ONLY INVENTORY / IMAGE QUALIFICATION HOLD
Baseline: `0ec4724` (92DE accepted local profile)

## Observed platform mismatch

The existing receiver adapters pin Windows binaries:

- Kilo: `C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.8.3-win32-x64\bin\kilo.exe`
- OpenCode: `C:\Users\David\AppData\Local\hermes\node\node_modules\opencode-ai\bin\opencode.exe`

The installed Docker CLI is 29.6.2. Its configured Linux-engine pipe was
unavailable on 2026-10-06. No daemon platform or image inventory could be
qualified. A Linux container cannot inherit the Windows executable hashes,
file IDs, AppContainer evidence, or native launch flags. A Windows-container
route would likewise need its own daemon/platform and image qualification;
neither route is selected here.

## Next bounded gate

After Docker Desktop is running, inspect only daemon OS/architecture,
installation mode, and existing local images. Do not pull, build, create,
start, or run a container in that inventory step. Select one receiver first,
then obtain its platform-compatible distribution and freeze its source,
version, dependency closure, image build recipe, platform-specific digest,
and entrypoint. The Kilo 7.8.3 Windows pin is historical evidence, not a
qualified Linux image identity. Keep OpenCode and Kilo qualification separate.

Only then freeze the versioned launch/admission contract and write fake-only
tests. The accepted 92DE threat model permits this design sequence, but it
does not authorize a real receiver or model call, or mark 92AT as passed.

`DOCKER_DAEMON_QUALIFIED=NO`
`CONTAINER_PLATFORM_SELECTED=NO`
`RECEIVER_IMAGE_PINNED=NO`
`DOCKER_RECEIVER_IMPLEMENTED=NO`
`PRODUCTION_READY=NO`
`LIVE_ACTIVITY=0`
