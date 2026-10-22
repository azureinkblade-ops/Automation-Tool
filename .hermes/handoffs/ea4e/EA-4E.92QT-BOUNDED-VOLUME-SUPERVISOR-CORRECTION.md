# EA-4E.92QT Bounded Volume Supervisor Correction

The 92QS independent review of the unwired 92QR supervisor returned source
HOLD. This checkpoint addresses only its deadline and exceptional cleanup
findings. It does not repair the mutable-path hash-before-spawn race.

The runner now carries the parsed UTC deadline through spawn, process wait,
reader joins, stream closure, and final result return. It denies a result
after the deadline even when the child has already exited. Reader creation
and startup are within post-spawn cleanup. On failure it attempts child
termination and wait independently, joins started readers, and closes both
streams when readers have stopped. Cleanup uncertainty remains a denial.

The fake-process qualification includes post-spawn expiry, reader startup
failure, and a failed kill whose wait and stream closure must still be
attempted. Focused tests: 13/13. Adjacent inert tests before final staging:
156/156. These tests do not prove Windows process-tree containment, protected
executable provenance, durable one-use authority, or a native volume read.

The 92QP native executable has not been run by this checkpoint. No Docker,
receiver, model, credential, GPU, ComfyUI, or production action occurred.
Independent review of the corrected committed source remains required.
Native qualification, trusted issuer, and production remain HOLD; strict
92AT mapped-byte proof remains REJECT.
