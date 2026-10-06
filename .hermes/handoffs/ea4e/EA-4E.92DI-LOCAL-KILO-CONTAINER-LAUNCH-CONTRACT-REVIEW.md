# EA-4E.92DI local Kilo container launch contract review

Status: NON-LIVE DESIGN REVIEW / LAUNCH CONTRACT NOT YET FROZEN
Baseline: `5dc284d7ea39cec724308eb685ca7257e250f466`
Date: 2026-10-06 (America/Phoenix)

## Scope and assurance boundary

This review concerns the operator-accepted local Docker profile only. Local
Windows administrators, SYSTEM, the Docker daemon/control account, the local
Hermes authority/store, and the image publisher are trusted. This profile
cannot defend against those actors. It must never be reported as the strict
92AT exact mapped-byte proof, which remains REJECT/HOLD.

92DH admits only metadata of a provisional image. Its `MATCH` result does not
authorize a container launch or establish `LOCAL_CONTAINER_PROVENANCE_CHECKED`.
The existing Kilo adapter remains a Windows executable launch path; none of
its runtime or authority identities may be silently reused for Linux Docker.

## Proposed launch contract, version 1

The future request must bind, before create, one delegation, one execution
authorization, one invocation authorization, one attempt, one receiver ID,
one exact image identity, one immutable launch-spec hash, and one unique
container name/label namespace. The issued authority must explicitly cover
the local-container profile. A metadata match or a prior Windows authorization
cannot create or widen that authority.

The launch spec must be canonical and deny unknown fields. It must include:

- Exact Linux/amd64 image identity and platform, fixed entrypoint and argv;
  the task may supply only the validated positional message, not CLI flags,
  model, agent, permissions, or shell syntax. No `--auto`.
- Non-root UID:GID 65532:65532, read-only root filesystem, no privileged mode,
  no host PID/IPC namespace, no Docker socket, no added capabilities, and no
  ambient host environment inheritance.
- An isolated, per-attempt writable HOME/config/tmp/workspace policy with
  explicit paths, ownership, mount type, content hashes, and cleanup owner.
  No repository, user home, host credential directory, or shared mutable
  runtime root may be mounted implicitly.
- A fixed minimal environment and deny-all Kilo agent/permission profile.
  The Windows `HOME`, `USERPROFILE`, `HOMEDRIVE`, `HOMEPATH`, `PATH`, and
  `SYSTEMROOT` material in `kilo_adapter.py` is not a Linux contract.
- A declared network mode and explicit model endpoint/credential delivery
  policy. Any network-enabled model run is a separately authorized live
  boundary. An inert smoke must use `network=none` and invoke no receiver.
- CPU, memory, pids, file-descriptor, disk/scratch, wall-time, stdout and
  stderr limits. The existing Windows defaults (60-second timeout, 4 MiB
  stdout, 128 KiB stderr) are reference values, not automatically qualified
  Docker limits.
- A one-attempt create/start/result accounting owner. Retrying a timed-out
  or uncertain create/start must reconcile daemon state under the same
  attempt identity before any new create. The adapter must not infer that
  absence of a response means absence of a container.
- Cancellation and crash recovery semantics: identify the exact container,
  stop/kill only that container, observe terminal state and bounded output,
  durably record the result, then perform separately accounted cleanup.
  Cleanup failure must remain visible and fail closed for reuse.

Before start, the trusted daemon must report the exact created container ID
and effective image, entrypoint/argv, user, mounts, environment keys, network,
capabilities/security options, resource limits, and labels. Any mismatch
denies start. After start, re-observe the same container identity and record
its terminal status, timestamps, exit code, output truncation, and cleanup
outcome. A tag, requested create spec, or host-side PID alone is insufficient.

## Findings blocking contract freeze

1. The provisional build reports image ID
   `sha256:cf003ba6e84cfd0fa8c2951dfe44454e25f9cf5e42eb6bf3ba82349b26b99120`.
   `docker image inspect` also displays a local `RepoDigests` entry with the
   same hash. This read-only observation does not by itself establish a
   separately verified, platform-specific distributable OCI manifest digest
   and dependency closure as 92DE requires. Define and test the exact digest
   semantics before granting provenance.
2. The image sets `HOME=/tmp/kilo-home` and `WORKDIR=/work`, but the current
   Dockerfile does not create a writable runtime home/workspace for the
   non-root user. It has not been tested as a running container.
3. The Windows Kilo adapter's argv, environment, profile file and transport
   contract are bound to a Windows executable. A separate Linux adapter and
   contract roll are required; changing the existing strict path is out of
   scope for this review.
4. The model endpoint, network egress, credential source, mount/scratch
   policy, numeric resource limits, and container result accounting owner
   have not been qualified. Do not fill these from ambient Docker defaults.
5. The inert container smoke was separately proposed but has not yet been
   explicitly authorized. No `docker run`, Kilo process, or model invocation
   occurred in this checkpoint.

## Next bounded action

Resolve the image identity semantics and runtime filesystem/config policy in
fake-only tests and source review. Keep all starts denied until a versioned
launch spec and daemon-observation checker are independently qualified. An
inert smoke and a real Kilo/model pilot remain distinct later approvals.

`LOCAL_CONTAINER_LAUNCH_CONTRACT_FROZEN=NO`
`LOCAL_CONTAINER_PROVENANCE_CHECKED=NO`
`CONTAINER_STARTED=NO`
`RECEIVER_EXECUTED=NO`
`MODEL_INVOKED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
