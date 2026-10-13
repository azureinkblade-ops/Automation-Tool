# EA-4E.92IY fake response release probe result

Status: PASS for one synthetic request, peer-gated fake release, and
dummy-client response delivery only.
Governing HEAD: `88c5bb59f9b7cd534a10b43a0c60544dc2301398`.
The operator separately approved one bounded fake-response release probe.
That approval was consumed by this run; there was no retry.

The pinned gateway image was
`sha256:afdd2f974bb91d8b3c9bc8da6dd2ac4c2667d4fe1c4e756b0e818e9eff5cd511`
and the pinned dummy Node client image was
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.
The run created one fresh internal-only bridge network and two temporary
containers. The exact pre-start image, label, network, read-only root,
zero mounts and port bindings, dropped capabilities and
no-new-privileges checks passed before either container started. There
were no credentials, provider configuration, Kilo/OpenCode receiver,
model, GPU/ComfyUI, host-published port, or production activation.

The dummy client sent one 205-byte 92IS-shaped synthetic POST. The gateway
reported one pending event for `ea4e92iy-synthetic`; its request digest
was `05bdede8d5f9b10a2a2e921ee427df3567f796ed0f22355893a6171c4d9de789`.
The event peer was `172.19.0.3`, matching the dummy client's fresh
daemon-observed IP on the exact created network while both containers
were running. Only after that match did the command send one SIGUSR2 to
the exact created gateway ID. The gateway and client both exited code 0.
The client emitted one line, `FAKE_RESPONSE_MATCH`, after checking HTTP
200 and SHA-256 equality to the pinned synthetic SSE response. The
gateway emitted only the one pending-event line.

The probe script did not print the configured synthetic response digest,
so the recorded transcript does not independently replay that exact
response-byte comparison. The in-run client check passed; do not promote
this evidence to a fully sealed cryptographic response artifact. The
reported peer-to-client-IP comparison is daemon network-membership
evidence, not independent socket-owner attestation.

Exact cleanup IDs:

```ini
network_id=9194dff51b9d1affab844dbe7c994c0d02d4a6d9d7e96a81f233026578f18126
gateway_id=e999fccf1a1f9c26f1a32c381a726f3952663a22c609b072cbf654a930754592
client_id=c6e072ae3afe5680908f61c5d0b3afd2d63020d9d2b0f40ecd57d0ed240de451
```

The command removed those exact containers and network. Follow-up
read-only queries by ID found none. No unrelated Docker object was
removed.

This qualifies a fake-only delivery path, not trusted request-scoped
production release, real Kilo SDK request compatibility, a real Kilo or
OpenCode model invocation, receiver result lineage, or an agent-to-agent
handoff. The local-container alternative still needs governed receiver
qualification and production activation. Strict 92AT mapped-byte proof
remains HOLD under its original threat model. Production remains HOLD.
