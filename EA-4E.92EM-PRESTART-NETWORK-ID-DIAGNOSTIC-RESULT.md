# EA-4E.92EM Prestart Network-ID Diagnostic Result

Status: diagnostic completed; peer qualification HOLD.

The separately approved one-shot diagnostic ran on committed source
`eaf36446051bd378d65c170524b365ae8237a1d8`, using provisional image
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.
Run ID: `04a73506d78a4d4ca0acbfa277af8e31`.

The diagnostic created one internal network, ID
`45e82ef37b1ad17e1c0ab1e6abc69c11b9585cb3e111f94f32bdb931062103b4`,
and two never-started helper containers. Both container inspect records named
the intended network in `NetworkSettings.Networks`, but both had an empty
endpoint `NetworkID`. The created-check denied the first one with
`gateway endpoint network ID denied`. This identifies the 92EJ mismatch:
Docker did not populate the endpoint network ID at the created lifecycle
point. It does not prove the later running network binding.

`containers_started=0`; `release_signals_sent=0`; no marker request, receiver,
model, or production activation occurred. The tool removed the exact created
container and network IDs. A separate read-only label-filtered Docker check
returned no remaining network or container for the run ID. The one-shot
diagnostic approval is consumed and must not be reused.

Next non-live boundary: review a two-stage contract in which prestart checks
enforce named network attachment and host policy without treating a blank
prestart endpoint ID as a verified binding, while a fresh running-state
observation must establish the exact network ID and socket peer before any
release signal. This needs explicit tests and review. No new live probe is
authorized by this result. Exact mapped-byte proof remains REJECT, and
production remains HOLD.
