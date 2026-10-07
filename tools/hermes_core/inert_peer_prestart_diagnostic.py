"""Diagnostic-only create/inspect sequence; never starts a container."""

import json
import sys
import uuid

from tools.hermes_core.inert_peer_created_check import (
    InertPeerCreatedDenied,
    inspect_inert_peer_created,
)
from tools.hermes_core.inert_peer_probe_docker import DockerProbeDriver
from tools.hermes_core.inert_peer_probe_plan import (
    IMAGE_ID,
    build_inert_peer_probe_plan,
)
from tools.hermes_core.inert_peer_probe_preflight import inspect_inert_peer_preflight


def _network_field(container, network_name, expected_id):
    settings = container.get("NetworkSettings")
    if type(settings) is not dict:
        settings = {}
    networks = settings.get("Networks")
    if type(networks) is not dict:
        networks = {}
    endpoint = networks.get(network_name)
    if type(endpoint) is not dict:
        endpoint = {}
    observed_id = endpoint.get("NetworkID")
    return {"attachment_names": sorted(key for key in networks if type(key) is str),
            "endpoint_network_id": observed_id if type(observed_id) is str else None,
            "endpoint_network_id_matches": observed_id == expected_id}


def diagnose_prestart(driver, run_id):
    plan = build_inert_peer_probe_plan(run_id)
    image = driver.inspect_image(IMAGE_ID)
    inspect_inert_peer_preflight(plan, image, driver.network_names(),
                                 driver.container_names())
    network_id = gateway_id = client_id = None
    cleanup_errors = []
    try:
        network_id = driver.create_network(plan["network_create"])
        gateway_id = driver.create_container(plan["gateway_create"])
        client_id = driver.create_container(plan["client_create"])
        network = driver.inspect_network(network_id)
        gateway = driver.inspect_container(gateway_id)
        client = driver.inspect_container(client_id)
        if (network.get("Id") != network_id
                or gateway.get("Id") != gateway_id
                or client.get("Id") != client_id):
            raise ValueError("created inspect identity denied")
        try:
            inspect_inert_peer_created(plan, image, network, gateway, client)
        except InertPeerCreatedDenied as exc:
            decision, reason = "PRESTART_HOLD", str(exc)
        else:
            decision, reason = "PRESTART_MATCH_ONLY", None
        return {"decision": decision, "reason": reason,
                "network_id": network_id,
                "gateway": _network_field(gateway, plan["network_name"], network_id),
                "client": _network_field(client, plan["network_name"], network_id),
                "containers_started": 0, "release_signals_sent": 0}
    finally:
        for identity in (client_id, gateway_id):
            if type(identity) is str and identity:
                try:
                    driver.remove_container(identity)
                except Exception as exc:
                    cleanup_errors.append(exc)
        if type(network_id) is str and network_id:
            try:
                driver.remove_network(network_id)
            except Exception as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise RuntimeError("diagnostic cleanup failed") from cleanup_errors[0]


def main(argv):
    if argv != ["--approved-diagnostic-once", IMAGE_ID]:
        raise ValueError("exact diagnostic acknowledgement required")
    run_id = uuid.uuid4().hex
    driver = DockerProbeDriver()
    print(json.dumps({"run_id": run_id, "status": "DIAGNOSTIC_STARTING"}), flush=True)
    try:
        result = diagnose_prestart(driver, run_id)
    except Exception:
        print(json.dumps({"run_id": run_id, "status": "HOLD",
                          "remaining_network_ids": sorted(driver.owned_networks),
                          "remaining_container_ids": sorted(driver.owned_containers)}),
              flush=True)
        raise
    print(json.dumps({"run_id": run_id, **result}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
