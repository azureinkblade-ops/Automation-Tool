# EA-4E.92TF Docker start exit-128 HOLD

Date: 2026-10-27

The user authorized exactly one tags-only native startup diagnostic at
`18c294af933fa0b53abf836033e07e14608ba3bf`. Fresh preflight matched
the pinned entrypoint, runner, and Docker CLI hashes; validated the six
model files and empty `manifests-v2`; confirmed the pinned Linux/amd64
image ID; and found no old EA-4E smoke container.

The one invocation created and inspected its exact-owned container.
`docker container start` then failed. The bounded start-stderr classifier
reported `unclassified`; exact-owned stopped-state reinspection reported
`exit_code=128`, `oom=false`, and combined `startup_category=unclassified`.
The combined value does not establish whether the bounded log read was
unavailable or unclassified. These fixed fields do not establish a root
cause. No raw
stderr or log text was reported. The launcher stopped before interface
inspection, `/api/tags`, or any inference. No GPU assignment, receiver,
agent handoff, cloud call, or production activation occurred.

Exact-owner cleanup completed. A separate read-only Docker query found
no remaining `ea4e92rm-` container. No retry was made; the one-run
authorization is consumed. The 16 KiB Docker-local log setting does not
prove a hard disk bound or zero retention. The cause remains unknown.
Further native diagnosis requires a separately governed, precisely
bounded design and fresh exact authorization. Production remains HOLD.
