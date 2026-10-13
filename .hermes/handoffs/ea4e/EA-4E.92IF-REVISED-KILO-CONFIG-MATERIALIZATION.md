# EA-4E.92IF Revised Kilo Config Materialization

Status: NON-LIVE / REVISED DUMMY FILES STAGED / PRODUCTION_READY=NO.
Baseline: `93777d7bb23c67b853ee697697d3ae453d19c45f`.

The 92IE fake-network candidate produces config bytes different from the
92DP/92IC v1 dummy files. 92IF stages those exact revised bytes into a new
isolated temporary root with separate reviewed input and writable runtime
copies. It binds the manifest to the accepted attempt and 92IE candidate
hash. Readback revalidates the 92IB reservation and current authority,
rejects v1 input manifests, rehashes both copies, and denies changed paths or
bytes. The original 92DP materializer and verifier retain their behavior.

The shared internal file writer and verifier continue to reject symlinks and
Windows reparse points and now reject planned paths containing `..`. No
existing state files were overwritten or deleted. Test-created temporary
roots remain test data.

Focused 92IF/92DP/92DR/92IE tests: 39 passed. Affected 92DP/92DR/92H/92I
ladder: 158 passed, zero failed. Tests cover distinct revised config copies,
the fake gateway URL, old-v1 substitution, changed runtime bytes, and
cancellation after preparation.

The prepared files are not a durable admission record or proof of effective
Docker mounts. No container, receiver, gateway, credential, network call,
model, GPU, ComfyUI or production activation was used. Next, a trusted owner
must bind exact image/config/network/peer metadata, enforce one-attempt
create/start and containment, and retain bounded terminal bytes. Real model
and credential qualification and exact live authorization remain separate.
