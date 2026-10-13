# EA-4E.92IP Fake Ping Gateway Bootstrap

Status: NON-LIVE SOURCE CANDIDATE / IMAGE NOT BUILT / NO START.
Baseline: `1672eae464e04e5232deb5a8cd633a296c171a66`.

The versioned 92IO gateway now has an explicit fake-only environment
bootstrap and a source-only Docker recipe based on the existing digest-pinned
Node base. It refuses malformed/noncanonical response bytes, digest drift,
and task/receipt lineage mismatch before opening a listener. A configured
one-request server retains hold/release and denial behavior. The old 92EW
gateway, image identity, and historical probe remain unchanged.

The `EA4E_QUALIFICATION_ONLY=1` marker is a fail-closed configuration check,
not execution authority. Response bytes in the container environment are
visible to the trusted Docker administrator under the accepted local profile.
The server does not itself attest the connected container; a future
request-scoped coordinator must establish the exact Docker network/peer and
authorization before sending its one release signal. No production route
imports or starts this image. No image digest is yet qualified.

Node source tests: 5 new-version tests and 6 old-version tests, all passed.
No Docker build/start, Kilo/OpenCode receiver, model, credential, GPU/ComfyUI,
result delivery, or production activation occurred. A bounded real receiver
probe is separately governed; strict 92AT mapped-byte proof remains HOLD.
