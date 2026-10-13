# EA-4E.92IG Fake Kilo Prestart Candidate Comparison

Status: NON-LIVE / SYNTHETIC METADATA ONLY / START DENIED.
Baseline: `4ac7848965c7121fe6e4432bc05b4c7a4f800532`.

The new pure checker rebuilds the 92IE candidate from the currently valid
92IB reservation, rechecks the separate 92IF input and runtime bytes, and
compares supplied created-container metadata with the pinned image/index,
Kilo entrypoint and argv, identity, candidate environment, read-only rootfs,
proposed network name, and three proposed mounts. It rejects additional
ports, host-access fields, duplicate env keys, malformed network settings,
extra mounts, and a non-created state.

It returns `CANDIDATE_METADATA_ONLY_START_DENIED` on a synthetic match.
The returned `MATCH` does not mean start permission or provenance: there is
no Docker client, daemon read, container create/start, gateway call, receiver
process, model invocation, credential, or production activation here.

Focused synthetic cases: 19 passed. Affected 92DH/DP/DR/92H/92I
ladder: 205 passed, 0 failed. Post-commit verification must be recorded
separately after commit.

Still open before a separately authorized bounded receiver probe:

- Bind a real daemon-observed network ID, gateway peer/accepted socket, and
  exact attempt owner, not merely a candidate network name.
- Qualify actual tmpfs ownership/options, HOME permissions, image-derived
  environment, resource/security limits, and the config Kilo really reads.
- Keep a one-shot claim/fence and bounded terminal output under a distinct
  execution owner; qualify fake-gateway response/body compatibility.
- Qualify OpenCode independently. This Kilo comparison cannot stand in for
  its executable, transport, or model behavior.

The accepted local-container threat profile is not strict 92AT mapped-byte
proof. Strict mapped-byte creation remains HOLD. No real receiver/model,
GPU/ComfyUI, or production activation is authorized by this checkpoint.
