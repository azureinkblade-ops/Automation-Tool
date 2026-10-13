# EA-4E.92IW next fake request/peer probe design

Status: DESIGN ONLY / NO DOCKER OBJECTS OR RECEIVER AUTHORIZED.
Governing checkpoint: `6db1574382a8358137570e0f79e5c8c804064012`.

92IV qualified only the versioned gateway's isolated start and no-request
idle expiry. The historical 92EZ client sends only `{"model":"ea4e-inert"}`;
the versioned 92IS gateway must reject that short body. Reusing the old
probe unchanged would not test a successful request path.

The next bounded qualification should exercise one dummy request without
Kilo, OpenCode, a provider, a model, or release authority:

1. Pin gateway image index
   `sha256:afdd2f974bb91d8b3c9bc8da6dd2ac4c2667d4fe1c4e756b0e818e9eff5cd511`
   and existing dummy Node client image
   `sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.
   Verify the gateway source label, both image IDs, and each effective
   entrypoint and user before creating anything. Do not assume the
   historical gateway's digest or request body applies to this version.
2. Create one fresh, labeled, internal-only Docker bridge network and at
   most two fresh, labeled containers. Use no host-published ports, mounts,
   credentials, provider configuration, GPU, or host networking. Apply
   read-only root, dropped capabilities, no-new-privileges, and bounded
   CPU/memory/PID limits. Inspect each exact created ID and the network ID
   before starting either container. A mismatch ends the attempt with
   exact-ID cleanup and no start.
3. Start the gateway, then the dummy client. The client sends exactly one
   bounded POST to `/v1/chat/completions` over the internal network using
   the 92IS seven-field `ea4e-inert` streaming shape with synthetic
   system/user messages. The gateway uses only synthetic attempt/task/
   receipt identities and a pinned fake SSE response. No receiver binary
   or interactive login is mounted or invoked.
4. Observe one pending event with the expected attempt, response digest,
   request byte length, and request SHA-256. Bind the event's peer IP to
   the client container using fresh daemon network and container inspect
   records. A reported IP alone is not an authoritative socket-owner
   attestation; record that limit explicitly. No SIGUSR2 release is allowed
   in this probe. The client/gateway may exit on bounded timeout; a 200
   response must be treated as an unexpected failure, not a success.
5. Enforce a host deadline and collect bounded logs/inspect records. Stop
   only still-running exact created IDs, remove only those IDs and the
   exact created network ID, then verify their absence. Preserve unrelated
   Docker objects, including the pre-existing LibreChat stack.

Acceptance is limited to request ingestion, pending-event lineage, and
daemon-observed network membership under the local-container alternative
threat model. It does not qualify exact socket ownership, release authority,
SSE delivery, a real Kilo SDK request, result return, OpenCode, production
activation, or strict 92AT mapped-byte proof. A separately approved later
probe is needed for release and receiver behavior. This design does not
authorize creating a network or container, starting a process, sending a
request, or invoking any model.
