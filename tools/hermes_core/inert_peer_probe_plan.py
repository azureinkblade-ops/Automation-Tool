"""Pure 92EA Docker command plan; no Docker or receiver execution."""

import re


IMAGE_ID = "sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682"


def build_inert_peer_probe_plan(run_id: str) -> dict:
    if type(run_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("run ID must be 32 lowercase hex characters")
    suffix = run_id
    network = f"ea4e-peer-{suffix}"
    gateway = f"ea4e-peer-gateway-{suffix}"
    client = f"ea4e-peer-client-{suffix}"
    common = [
        "--network", network,
        "--pull", "never",
        "--platform", "linux/amd64",
        "--restart", "no",
        "--user", "node",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--pids-limit", "32",
        "--memory", "256m",
        "--cpus", "0.25",
        "--label", f"hermes.ea4e.run={run_id}",
    ]

    def container(name, mode):
        return ["docker", "container", "create", "--name", name,
                *common,
                *(["--network-alias", "ea4e-peer-gateway"] if mode == "gateway" else []),
                IMAGE_ID, mode]

    return {
        "schema_id": "hermes.ea4e-inert-peer-probe/v2",
        "run_id": run_id,
        "image_id": IMAGE_ID,
        "network_name": network,
        "gateway_name": gateway,
        "client_name": client,
        "network_create": ["docker", "network", "create", "--driver", "bridge",
                           "--internal", "--label", f"hermes.ea4e.run={run_id}",
                           network],
        "gateway_create": container(gateway, "gateway"),
        "client_create": container(client, "client"),
        "start_order": [gateway, client],
        "expected_request": {"method": "GET", "path": "/marker", "count": 1},
        "release_signal": "SIGUSR2",
        "release_target": "exact_created_gateway_id_after_pending_peer_match",
        "observations_required": [
            "image_and_platform", "network_internal_and_membership",
            "both_container_ids_and_states", "no_published_ports_or_mounts",
            "gateway_socket_peer_while_request_pending",
            "fresh_running_daemon_snapshot_before_release",
            "signal_exact_gateway_id_only_after_match",
            "client_marker_and_exit", "post_exit_membership",
        ],
        "cleanup": "exact_created_container_ids_then_exact_created_network_id_only",
        "max_containers": 2,
        "max_networks": 1,
        "timeout_seconds": 45,
        "max_log_bytes_per_container": 4096,
        "probe_authorized": False,
        "kilo_receiver_executed": False,
        "model_invoked": False,
        "production_ready": False,
    }
