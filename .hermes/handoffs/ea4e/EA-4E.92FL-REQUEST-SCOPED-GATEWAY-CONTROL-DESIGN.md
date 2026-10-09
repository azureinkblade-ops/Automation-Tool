# EA-4E.92FL Request-Scoped Gateway Control Design

Status: NON-LIVE DESIGN CANDIDATE / IMPLEMENTATION AND LIVE USE HOLD
Baseline: `a1c42fd81a09a1560b78ec25e06f7d785748598c`
Date: 2026-10-08 (America/Phoenix)

## Purpose and boundary

92FI and 92FJ/92FK qualify only created metadata and an inert, synthetic
pending-request observation. The 92DW dynamic fake gateway owns host-side
body-shape validation and the durable one-send claim, but has no accepted
socket. This design connects those boundaries without changing the 92CN
exact-body-hash fixture or claiming 92AT mapped-byte proof. The accepted
92DE local-Docker profile trusts host administrators and the Docker daemon;
`LOCAL_CONTAINER_PROVENANCE_CHECKED` remains unearned.

## Proposed ownership

- A pinned, per-attempt **container gateway** owns the private-network HTTP
  listener, exact accepted socket, bounded request buffer, and fake response
  channel. It cannot issue or claim execution/invocation authority and holds
  no upstream credential.
- Hermes on the host owns the delegation/attempt/authorization lookup,
  cancellation and revocation checks, body validation, fresh Docker peer
  reads, durable one-send claim, and release decision. Only Hermes can
  produce a claim receipt. The receiver receives a distinct child-only token.
- A pinned control helper is launched by exact gateway container ID using
  Docker exec with stdin/stdout, no shell, no published port, and no task text
  in argv. It talks only to a loopback/Unix control endpoint inside that same
  gateway container. A per-attempt control secret is provisioned over this
  channel before the receiver starts; it is not placed in argv, environment,
  image, logs, or receiver mounts. Docker-control principals are trusted under
  92DE; this is not protection from a host administrator.

## One request lifecycle

1. Bind source commit, pinned platform image/index, exact container/network
   IDs, delegation ID, ExecutionAttempt ID, invocation authorization ID,
   child-token digest, TTL, and a fresh run ID. Create only the reviewed
   private network and gateway; verify effective config and bootstrap the
   one-attempt control secret before opening the HTTP listener. Start the
   separately qualified receiver only after that acknowledgment.
2. The gateway accepts at most one `POST /v1/chat/completions` from its socket,
   caps raw bytes before parsing, and holds that exact connection pending.
   It assigns a fresh request nonce and computes the body digest. It must not
   trust a forwarded peer header, caller-supplied container ID, or bearer
   token as peer proof. It writes neither raw body nor credential to logs.
3. The host obtains the pending body only through the pinned authenticated
   control helper. A canonical, length-bounded frame binds run ID, request
   nonce, accepted-socket peer, body length and digest, and frame sequence;
   HMAC authenticates the frame. The host verifies the actual body digest,
   strict schema, method/path/content type, exact model/stream/tool policy,
   nested limits, duplicate keys and finite numbers. The body cap is **not**
   raised from 65,536 until a separate measured-headroom review. Raw body is
   held in memory only and is not durable evidence.
4. Before a claim, Hermes reads fresh network, gateway, and receiver records
   by exact IDs at pending observation and again immediately before claim.
   It requires one isolated
   network, exact running members and image/config pins, no host port or
   extra attachment, and accepted-socket IP equal to the receiver endpoint.
   It rechecks authority, TTL, cancellation, and revocation immediately
   before the durable one-send claim.
5. Hermes atomically claims the one-send budget keyed by the exact attempt,
   invocation authorization and request nonce/body digest. Only after a
   durable claim may it send one authenticated release frame. That frame
   binds the claim receipt, run ID, request nonce, body digest, response
   digest, and sequence. The gateway accepts it only for the still-pending
   socket and returns the pinned **fake** response. No signal-only release.
6. Any denial or uncertainty after claim leaves the budget consumed. A
   timeout, control-channel break, gateway crash, ambiguous response, or
   cancellation never refunds or silently retries the send. The host
   reconciles exact run-owned Docker objects and stores only bounded identity,
   digest, decision, and cleanup evidence. A later real upstream send and a
   real Kilo/model pilot require separate contracts and authorization.

## Required fake-only qualification before runtime

Test wrong/duplicate nonce, stale or reordered frame, bad HMAC, changed body
between frames, extra network member, stopped or replaced receiver, changing
endpoint across the two reads, cancellation before/after claim, concurrent
claims, duplicate release, lost control acknowledgment, gateway crash, and
cleanup failure. Tests must prove no fake response before durable claim and
no refund after an ambiguous send. Keep the existing 92CN fixture unchanged.

The first implementation slice is a pure v1 control-frame codec. It uses a
four-byte big-endian canonical-JSON header length, a bounded canonical header,
a four-byte body length, the raw pending body (empty for release), and a
32-byte HMAC-SHA256 tag over a domain-separated payload. Its pending frame
binds the exact run, source, network/gateway/receiver IDs, request nonce,
accepted-peer address, body digest/length, and sequence 1. Its release frame
adds claim-receipt and response digests with sequence 2. The key is injected
as 32 bytes; neither encoding nor decoding manages keys or replay state.
It preserves the existing 65,536-byte cap and grants no authority. Sixteen
pure tests pass, including tampering, duplicate/noncanonical header, wrong
identity, body-cap and release-shape denials. No Docker or model call occurs.

Open implementation decisions: bootstrap transport and secret lifecycle,
durable claim receipt schema, measured body cap, and Linux receiver identity.
This design and codec are not authorization to start
Kilo/OpenCode, call a model, run a GPU, or activate production.

`GATEWAY_PLACEMENT=CONTAINER_CANDIDATE_ONLY`
`HOST_DURABLE_CLAIM_OWNER=HERMES`
`PURE_CONTROL_FRAME_CODEC=YES_NONLIVE`
`CONTROL_TRANSPORT_IMPLEMENTED=NO`
`REAL_RECEIVER_AUTHORIZED=NO`
`PRODUCTION_READY=NO`
