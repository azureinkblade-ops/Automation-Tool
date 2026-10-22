# EA-4E.92QV Reader-Start Tracking Correction

The 92QU independent review of 92QT returned source HOLD. This narrow
change addresses only its reader-start registration edge: the thread object
is registered before `start()`, and cleanup checks whether it is alive
before joining. A fake launch-then-raise test verifies that the registered
reader is observed and joined before its pipe is closed. The ordinary
pre-launch start-failure test remains covered.

Focused fake-process tests: 14/14. Adjacent inert matrix before staging:
157/157. These are source/fake-process results only. The corrected blob
requires its own independent review before a source PASS could be claimed.

The 92QU medium finding remains unresolved: synchronous executable hashing,
process spawn, and stream closure can block without a hard elapsed-time
bound. Additional wall-clock checks inside this same process cannot make
those operations preemptible. A separately reviewed containment mechanism
would have to bound the whole operation, treat deadline expiry or uncertain
cleanup as a permanent denial, and bind the launched image and dependencies
to a protected installation. No such mechanism is implemented here.

No native volume probe, Docker mutation, Kilo/OpenCode receiver, model,
credential, GPU, ComfyUI, or production action occurred. Trusted issuer and
production remain HOLD; strict 92AT mapped-byte proof remains REJECT.
