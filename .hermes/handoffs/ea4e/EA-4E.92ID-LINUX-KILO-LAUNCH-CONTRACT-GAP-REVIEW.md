# EA-4E.92ID Linux Kilo Launch Contract Gap Review

Status: NON-LIVE DESIGN REVIEW / CONTAINER START HOLD.
Baseline: `9332981825a602527c622c3046fa02606b2f1e08`.

The 92IB reservation and 92IC mount candidate bind the accepted task to
reviewed dummy config source bytes. They do not form an executable container
contract. Source review found concrete contradictions that must be resolved
before any owner may create or start a Kilo receiver:

1. `local_kilo_inert_plan.py` sets the receiver endpoint to
   `http://fake-gateway.invalid/v1`, while the qualified fake gateway probe
   uses the internal network alias `ea4e-fake-gateway`. The receiver has no
   demonstrated route to the configured endpoint. A later real provider must
   be selected by the trusted gate, never by the delegated task.
2. The plan declares both `/tmp/kilo-home` and `/work` writable under a
   read-only root filesystem. 92IC proposes a writable mount for HOME only;
   `/work` has no writable mount. Effective HOME and workspace permissions
   remain unqualified.
3. Config delivery is explicitly `UNRESOLVED_NO_FILES_WRITTEN` in the plan,
   even though 92DP can prepare separate input and runtime copies. 92IC
   records proposed sources but does not bind an effective Docker mount or
   Kilo's observed config rewrite.
4. Network binding is explicitly `UNRESOLVED_FAKE_ONLY`. The successful inert
   peer probe used helper images, not the delegated Kilo image. No accepted
   socket, fresh daemon network membership, and task-bound one-send claim are
   jointly observed for Kilo.
5. `inspect_prestart_image_binding()` checks image/index and `created` state,
   not effective Kilo argv, environment, mounts, resource limits, network,
   peer, or container ownership. A match from that checker cannot be used as
   a start decision.

The narrow next implementation is a separate versioned resolved-launch
candidate, not an edit to the v1 reserved plan or a reinterpretation of its
`launch_authorized=False`. Its preimage must bind the v1 plan and intent
hashes, exact image/index, effective argv and environment, immutable reviewed
input bytes, writable runtime HOME and workspace policy, exact internal
network and gate identity, resource/security limits, and one-attempt owner.
The gate must hold any upstream credential; the receiver may receive only a
request-scoped dummy token. The candidate itself must remain non-launchable.

Only after that candidate exists may a pure prestart checker compare trusted
daemon-observed image, config, mounts, state and network with it. One-shot
claim/fence, process start, retained bounded output, containment and result
return require a distinct owner and exact authorization. OpenCode needs its
own runtime/image/config qualification; Kilo evidence cannot stand in for it.

No Docker, receiver, model, credential, GPU, ComfyUI or production state was
changed for this review. The accepted local-container profile is still
distinct from the strict 92AT mapped-byte requirement, which remains HOLD.
