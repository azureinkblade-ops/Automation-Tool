# EA-4E.92CS fresh shape-probe launch gate

Status: NON-LIVE VALIDATION PASS / RECEIVER LAUNCH DENIED
Baseline: `e4dd50504d0831faff6a46fb6463f0525d099d3b`

The 92CR dummy-only plan at
`C:\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo-shape-probe-92cr-20261004`
is now recognized by the 92CM runner's **read-only** validator with its
exact root and port 49322. The validator still reconstructs the pinned
binary, inert argv, isolated environment, dummy config, profile, and false
authority flags. It refuses any other root, config drift, binary hash
change, or existing one-shot claim.

`run_once()` explicitly rejects the fresh 92CR root after validation and
before opening a loopback listener, creating a claim, or starting Kilo.
An isolated test replaces server construction with a failure sentinel and
proves that refusal occurs first. The earlier 92CM root remains consumed
and cannot be replayed. Focused fake-only checks: 38 passed, 1 skipped
(the spent 92CM prepared-plan check). The combined affected Kilo,
streaming, and admission gate passed 204 tests with 2 skips.

This does not authorize a new Kilo process. To enable an exact one-shot
shape probe, the operator must first authorize the specified fresh plan,
executable/config hashes, host-egress risk, one process, timeout, output
cap, no retry, and sanitized event capture. Only then may a separate,
reviewed launcher change permit this root. No real provider credential,
model call, production activation, GPU, or ComfyUI work is authorized.
The same-user peer-identity decision and 92S mapped-byte HOLD remain open.
