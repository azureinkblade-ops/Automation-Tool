# EA-4E.92JF Docker inspect transport contract

Status: FAKE-RUNNER QUALIFIED / NO CONCRETE DOCKER RUNNER / NO START.
Governing predecessor: `08800d87303b451f95bc5a5cfa096bfe71efef82`.

This default-disabled client defines only three exact-ID Docker CLI reads:
container inspect, linux/amd64 image inspect, and network inspect under
`desktop-linux`. It validates 64-hex container/network IDs, a sha256 image
reference, pinned executable bytes, a 5-second requested timeout, and a
1 MiB returned-output cap. It parses one JSON object in a one-element
array, rejecting invalid UTF-8, duplicate keys, non-finite values, wrong
identity, and extra objects. There is no shell composition or create/start/
signal operation. No command runs unless a runner is explicitly injected.

The installed Docker CLI's local `--help` confirmed the three inspect
forms; that help query did not inspect the daemon. The fake runner tests
check exact argv, bounds, changed executable denial, identity validation,
and malformed outputs. The first test collection failed because a 1 MiB
parameter value generated an oversized pytest case ID on Windows; the case
now uses a short marker and constructs the bytes in the test body. The
corrected focused run passed 17 tests after the non-finite JSON addition.
The adjacent fake-only ladder passed 300 tests.

The injected runner remains responsible for enforcing timeout, output cap,
environment isolation, and process cleanup. This module checks the returned
bytes but cannot prove those runner properties. No concrete subprocess or
Docker SDK binding is present, and no daemon/container/receiver/model was
invoked. Its output is still local-container-profile evidence only, not
strict 92AT mapped-byte proof. Production remains HOLD.

The equality check between image inspect `Id` and the pinned manifest digest
is a contract assumption, not a daemon-qualified fact. Docker may expose an
image config digest there instead of the manifest/index digest. A bounded
read-only daemon observation must establish the mapping before this client
can be used as real image provenance evidence; do not loosen identity checks
based on fake-runner results.
