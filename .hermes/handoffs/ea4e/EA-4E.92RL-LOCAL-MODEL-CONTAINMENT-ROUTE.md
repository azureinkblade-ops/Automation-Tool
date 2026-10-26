# EA-4E.92RL Local Model Containment Route

Status: WINDOWS HOST LAUNCHER HOLD / CONTAINER ROUTE CANDIDATE ONLY.
Source baseline: `657b3f7d84f12f176b55088e519b39c5a31e6798`.

An independent, read-only review of the 92RK prestart hold and committed
92S source found that the existing zero-capability AppContainer probe is
designed to deny loopback as well as non-loopback connections. It cannot
qualify a localhost-reachable Ollama server. The 92S creator, pre-resume
verifier, capture loop, and cleanup controller remain injected or partial;
the current one-process, 256 MiB Job is a probe limit, not a model limit.
No native launcher was qualified by this review.

The Windows route remains HOLD until a separately reviewed transport can
allow only the required loopback exchange without a machine-wide loopback
exemption, firewall mutation, or broader network capability. Merely adding
the creation-time Job attribute would not close this network gap.

An alternative non-live design is a pinned Linux Ollama image in a Docker
container with `--network none`. Docker documents that this network mode
creates only the container-local loopback interface. A request broker could
use an exact, bounded `docker exec` call to reach the model server *inside*
the same container; no host port would be published. The container must be
created with reviewed memory, process, privilege, filesystem, restart, and
network settings before its server starts. The broker must verify the
effective container settings, enforce one-request and wall-clock budgets,
capture output incrementally, and stop the exact owned container on every
exit path. A stopped container may be retained for audit; no automatic
deletion is authorized.

This is an architecture candidate, not a qualified launcher. No pinned
Linux runtime image or model mount layout has been admitted. A Docker
Engine `none` setting alone is not observed runtime proof of the broker's
transport, resource enforcement, or exact cleanup. The existing approval
for a host-executable Ollama smoke does not cover this container route.
Before any container creation, image acquisition, model/GPU use, or real
handoff, pin and independently review the exact implementation and obtain
a new bounded authorization for that execution envelope.

The local `qwen3:14b` manifest and blob hashes remain recorded in 92RJ;
they are not a Linux Ollama runtime identity. No Ollama, Docker, model, GPU,
receiver, or production action occurred in this checkpoint.
