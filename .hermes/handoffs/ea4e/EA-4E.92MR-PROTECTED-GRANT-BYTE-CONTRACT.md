# EA-4E.92MR protected network-grant byte contract

Status: NON-LIVE CANDIDATE / PRODUCTION HOLD.
Parent: `3cab8327822cfb5b94c731807027ac77672506ce`.

This checkpoint introduces fixed, side-by-side pure contract methods for
`hermes.docker-network-mutation-grant/protected-v1` with
`hermes.ea4e.profile=LOCAL_CONTAINER_PROTECTED_ISSUER`. The earlier complete
fake candidate remains v2 and requires `FAKE_ONLY_LOCAL_CONTAINER`; its
public methods and the v4 fake store are unchanged. Each parser rejects the
other profile and schema. The protected parser also rejects invalid action,
driver, endpoint, internal flag, one-attempt budget, time window, identity,
labels, malformed or noncanonical bytes, extra fields, and mismatched
independently supplied expected values. Artifact SHA-256 is a byte-integrity
check, not an authorization signature or trusted-source proof.

Changed surface: `tools/Ea4eNetworkMutationGrantCandidate.cs`,
`tests/hermes_core/fixtures/ea4e92mr_protected_grant_probe.cs`, and
`tests/hermes_core/test_ea4e92mr_protected_network_grant.py`.

Working-tree qualification: focused protected/fake/builder suite 50/50;
existing v4 store, identity, request binding, and ceremony suite 61/61.
Only local compiler and test-probe processes ran. No Docker mutation, store
issuance, UAC, Kilo/OpenCode receiver/model, GPU/ComfyUI, or production
activation occurred.

This checkpoint does **not** qualify a production issuer. In particular,
`BuildProtectedCandidate` accepts caller-supplied fields, so an issuer must
obtain operator, binary, installation, policy, authority, and store values
from independently reviewed trusted observations. The production durable
store, protected installation, UAC ceremony, and exact bounded live grant
are separate checkpoints. Strict 92AT remains REJECT/HOLD.
