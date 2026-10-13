# EA-4E.92IE Versioned Fake-Network Kilo Candidate

Status: NON-LIVE / PURE CANDIDATE / PRODUCTION_READY=NO.
Baseline: `384e60f81df03bc3e3cb18c37cccefb5132677c2`.

The 92ID review found that the reserved v1 ping plan could not reach the
fake gateway and had no writable `/work` policy. The new 92IE candidate is a
separate schema derived only after 92IB revalidates the attempt and v1 plan.
It binds the v1 plan and reservation hashes, image/index, receiver argv and
identity, a deterministic per-attempt internal network name, the fake
gateway alias/URL, and a proposed non-root `/work` tmpfs policy. It parses
the v1 JSON config structurally, changes only the fake `baseURL`, and records
the exact revised config bytes and SHA-256. The original v1 object and its
reserved row are not changed.

The candidate remains dummy-only. It sets `source_bytes_prepared=False`,
`effective_config_checked=False`, `peer_qualified=False`,
`gateway_body_qualified=False`, `model_qualified=False`, and
`launch_authorized=False`. In particular, naming a gateway alias is not a
proof that the current fake gateway accepts Kilo's actual request body.
No new config files, network, Docker object, receiver, credential or model
call are created by the builder.

Tests cover deterministic revision, v1 immutability, revised config hash,
workspace policy, changed-plan denial, unreserved-attempt denial, and
cancellation. Focused tests: 19 passed. Affected 92DP/92DR/92H/92I ladder:
155 passed, zero failed. Existing strict Windows path and 92AT mapped-byte
HOLD are unchanged.

Next implementation boundary: materialize the revised config under isolated
source/runtime paths without reusing 92IC's v1 bytes; bind those paths to
this candidate, then compare exact effective daemon-observed config, mounts,
network and peer under one owner. Real provider/model qualification and an
exact bounded live authorization remain separate gates.
