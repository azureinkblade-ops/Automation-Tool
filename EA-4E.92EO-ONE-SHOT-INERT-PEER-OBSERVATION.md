# EA-4E.92EO One-Shot Inert Peer Observation

Status: inert peer observation completed; production remains HOLD.

The operator explicitly approved one bounded inert peer probe using committed
source `4158f1be3cfb255ddf076269ee228c0a98e20700` and image
`sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682`.
Before the run, local and remote source HEAD matched, the tracked tree was
clean, and read-only image inspect returned the exact pinned image ID.

Run ID: `29738531e8c245608f982efff29d2fcf`.
The bounded driver returned `INERT_PEER_OBSERVED_ONLY`, socket peer
`172.19.0.3`, `peer_qualified=false`, and `production_ready=false`.
It created network
`d174857afee189cc01c3d7be86c1e97b166764985b209fd263431911875809ab`,
gateway
`091c446b80c8c9ee12428b168a649cf19e3c025c0bf41126bfd9e5ffbaf35bba`,
and client
`97521867ab2149765221ebcaa0300042b383f174465f006e519020e0b3171c7e`.
The coordinator's success path requires the fresh running inspect/socket-peer
comparison, one gated SIGUSR2 release, successful helper exits, and the
client's fixed `MARKER_MATCH` line. The returned result is evidence of that
bounded local inert exchange, not a real Kilo/OpenCode invocation.

The driver attempted exact-ID cleanup before returning. A separate read-only
label-filtered Docker query found no remaining container or network for the
run ID. The one-shot approval is consumed; do not rerun under it.

This probe does not qualify executable image provenance, exact mapped-byte
proof, independent issuance, or production activation. The 92AT exact-byte
invariant remains REJECT; no Kilo/OpenCode/model/credential/GPU/ComfyUI work
or production activation is authorized by this result.
