# EA-4E.92DD local Docker alternative proposal

Status: PROPOSED CONTRACT REVISION / NON-LIVE / NOT ACCEPTED
Baseline: `ef2304b7df1f0837246b830ea3ffbb7c75302320`

## Decision requested

This is the faster local execution option requested by the operator. It is
not an amendment to the frozen 92CZ administrator-inclusive decision or the
92AT exact mapped-image-byte requirement. Those remain controlling for the
strict path until a separate, explicit acceptance authorizes this versioned
alternative. No production activation or live receiver/model call follows
from this proposal.

## Proposed threat model, local-container profile

Trusted: this Windows host's administrators and SYSTEM, Docker Desktop and
its daemon/backend, the operator's Docker-control account, host kernel and
hypervisor, the image builder/publisher, the Hermes authority process and
durable stores, and the installed receiver image. Compromise of any trusted
component is outside this profile. This explicitly reverses the 92CZ
administrator-in-scope assumption for this profile only; it does not claim
that Docker isolates work from this PC's administrators. A local administrator
can control Docker, local credentials, files, and the approval workflow.

In scope: accidental configuration drift, stale or substituted image tags,
untrusted task text and receiver output, ordinary network peers, replay,
duplicate launch, cancellation races, and non-administrator processes that
cannot access the Docker API or Hermes stores. A process with the operator's
Docker socket/API rights is effectively trusted, not an in-scope attacker.
This is a local operational-risk profile, not an independent trust boundary.

## Replacement claim, not byte attestation

Name the positive result `LOCAL_CONTAINER_PROVENANCE_CHECKED`. It means only
that the trusted Docker daemon was instructed once to start the reviewed
platform-specific image digest with the exact reviewed command, environment,
mounts, network, resource limits, and security settings, and that the
resulting container identity/configuration matched the request under the
trusted-daemon assumption. It does **not** claim that the exact process
image-section bytes were observed, that a file hash equals mapped bytes, or
that 92AT `VERIFIED_SUSPENDED` passed. The 92AT status stays REJECT/HOLD.

Candidate admission inputs: immutable platform-specific image digest plus
local image ID, exact entrypoint/argv and receiver version, working directory,
environment allowlist, provider credential scope, network policy, mount list,
resource ceilings, timeout, output ceiling, request hash, authorization ID,
one-attempt ID, and cancellation state. A mutable tag alone is never an
identity pin. No `docker.sock`, host root, privileged mode, host PID/network
namespace, or executable/config override mounts. Use a read-only rootfs,
least privilege, and explicit writable scratch only where receiver behavior
requires it. The actual Kilo/OpenCode image and its dependencies have not
been built or qualified, so these are proposed constraints, not passing
facts.

The receiver may call a model provider, so provider credentials and network
egress must be scoped to one bounded request. A container is not a model
budget control; issuer/store accounting must still enforce one attempt,
one send, cancellation, durable lineage, and post-crash reconciliation.
Approval on this trusted PC is sufficient only under this revised threat
model. It would not satisfy 92CZ's independent-operator requirement.

## Required implementation and verification sequence

1. Obtain explicit acceptance of this new threat model and named weaker
   claim. Preserve the strict path without relabeling its evidence.
2. Freeze a versioned Docker receiver contract and immutable image build,
   exact platform digest, dependency closure, daemon identity, and runtime
   configuration. The current Kilo/OpenCode adapters launch local binaries;
   no Docker receiver path exists in this checkpoint.
3. Fake-only tests deny mutable tags, digest/config mismatch, forbidden
   mounts/privileges, duplicate creates, stale authorization, cancellation,
   ambiguous daemon results, cleanup failure, and missing accounting. A
   fake must never mint a successful live provenance receipt.
4. With Docker running, separately authorize inert container integration
   checks. Capture daemon/server version, platform, image digest, container
   inspect evidence, audit, cleanup, and negative tests. These still do not
   authorize receiver/model use.
5. Separately authorize one bounded Kilo or OpenCode receiver/model pilot,
   then evaluate result lineage, one-send enforcement, recovery, and rollback
   before any default production enablement.

## Current host observation

On 2026-10-06, `docker.exe` was installed at
`C:\Program Files\Docker\Docker\resources\bin\docker.exe` (client 29.6.2),
but the Linux-engine named pipe was absent, so the daemon was not reachable.
No container was created, inspected, or run.

Docker references:

- https://docs.docker.com/engine/security/
- https://docs.docker.com/desktop/features/wsl/
- https://docs.docker.com/engine/security/rootless/

`ALTERNATIVE_THREAT_MODEL_ACCEPTED=NO`
`LOCAL_CONTAINER_PROVENANCE_CONTRACT_FROZEN=NO`
`DOCKER_RECEIVER_IMPLEMENTED=NO`
`EXACT_92AT_BYTE_PROOF=REJECT_UNCHANGED`
`PRODUCTION_READY=NO`
`LIVE_ACTIVITY=0`
