# EA-4E.92NC app-instance challenge observation contract

Status: NON-LIVE FAKE-ONLY CONTRACT CORRECTION / PRODUCTION HOLD.
Parent: `45d1ce9f9001ef5760704b539b6168c82ed2705d`.

The non-fake 92LQ owner previously constructed its process observation with
the nonce copied from the launch receipt. That did not independently observe
the nonce. It now requires a separate challenge collaborator. A live receipt
is returned only after the package observation, kernel process observation,
challenge nonce/PID/creation-time match, and a second unchanged live process
query. Missing, malformed, incomplete, mismatched, or throwing challenge
observations move the owner to UNKNOWN and deny automatic retry. A process
already observed exited still takes the existing one-time handle-close path.

Changed files:

- `tools/ea4e92lq_app_instance_owner.py`
- `tests/hermes_core/test_ea4e92lq_app_instance_owner.py`
- this evidence file

Focused current-tree gate: 53 passed, 0 failed. Adjacent app-owner, retained
handle, suspended-process, and native pipe-client gate: 132 passed, 0 failed.
The native pipe tests ran in the permitted environment because this host's
filesystem sandbox cannot connect the test pipe.

This is an injected contract with fake collaborators. There is no native
challenge observer, trusted launcher, installed app package, protected pipe,
or independent issuer behind it. A caller able to substitute the collaborator
can forge its result. The challenge must eventually be bound to the same
connected pipe client and issuer-owned ceremony; the receipt is not itself a
challenge proof. Strict 92AT mapped-byte proof remains REJECT/HOLD and the
accepted 92DE local-container provenance profile is separate. No app launch,
Docker mutation, real receiver/model, GPU/ComfyUI, or production activation
occurred.
