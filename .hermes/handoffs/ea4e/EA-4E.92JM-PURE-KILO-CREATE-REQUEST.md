# EA-4E.92JM pure Kilo create request

Status: NON-LIVE CREATE-REQUEST PROPOSAL / NO DOCKER MUTATION.
Governing predecessor: `d0f682583b7e6bd361e60db9efadb7b4184b7398`.

The 92JC spec verifier now feeds a pure Docker container-create argv
builder. It binds the reserved dummy attempt/spec hash and includes the
reviewed image index/platform, deterministic name/network, non-root user,
workdir, entrypoint/argv, labels/environment, two bind mounts with the
planned read-only distinction, read-only root, `/work` tmpfs, capability
drop, no-new-privileges, CPU/memory/pids, no restart, and pull=never.
The returned request is hashed and explicitly carries both
`create_authorized=false` and `launch_authorized=false`. It contains no
Docker executable path and no call site that executes the argv.

The builder rejects changed caller specs, unknown host-policy fields,
non-dummy credential class, and mount CSV delimiters in paths. The
focused pure tests passed 6/6; the adjacent fake-only ladder passed
322/322 before commit. `docker container create --help` was consulted
locally for option names; no create command was issued.

This is not a qualified effective-daemon contract: defaults, mounts,
network/gateway ownership, image selection, and Windows path handling
must be checked against read-only post-create observations. No durable
one-shot create claim or mutation owner exists yet. A real create-only
pilot still requires a separately reviewed exact authorization. The
original strict 92AT mapped-byte proof remains separate. Production
remains HOLD.
