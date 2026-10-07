"""One-shot inert peer sequence over an injected Docker-shaped driver."""

from tools.hermes_core.inert_peer_created_check import inspect_inert_peer_created
from tools.hermes_core.inert_peer_observation import inspect_inert_peer_observation
from tools.hermes_core.inert_peer_probe_plan import build_inert_peer_probe_plan
from tools.hermes_core.inert_peer_probe_preflight import inspect_inert_peer_preflight


class InertPeerProbeDenied(RuntimeError):
    pass


def run_inert_peer_probe(driver, run_id: str) -> dict:
    """Run one inert marker exchange; no receiver/model path exists here."""
    plan = build_inert_peer_probe_plan(run_id)
    image = driver.inspect_image(plan["image_id"])
    inspect_inert_peer_preflight(
        plan, image, driver.network_names(), driver.container_names())

    network_id = None
    gateway_id = None
    client_id = None
    cleanup_errors = []
    try:
        network_id = driver.create_network(plan["network_create"])
        gateway_id = driver.create_container(plan["gateway_create"])
        client_id = driver.create_container(plan["client_create"])
        if (not all(type(value) is str and value for value in
                    (network_id, gateway_id, client_id))
                or len({network_id, gateway_id, client_id}) != 3):
            raise InertPeerProbeDenied("created identity denied")
        network = driver.inspect_network(network_id)
        gateway = driver.inspect_container(gateway_id)
        client = driver.inspect_container(client_id)
        if (network.get("Id") != network_id
                or gateway.get("Id") != gateway_id
                or client.get("Id") != client_id):
            raise InertPeerProbeDenied("created inspect identity denied")
        inspect_inert_peer_created(plan, image, network, gateway, client)

        driver.start_container(gateway_id)
        driver.start_container(client_id)
        accepted = driver.wait_accepted_event(gateway_id, 10)
        network = driver.inspect_network(network_id)
        gateway = driver.inspect_container(gateway_id)
        client = driver.inspect_container(client_id)
        if (network.get("Id") != network_id
                or gateway.get("Id") != gateway_id
                or client.get("Id") != client_id):
            raise InertPeerProbeDenied("running inspect identity denied")
        inspect_inert_peer_observation(plan, network, gateway, client, accepted)

        driver.signal_gateway(gateway_id, plan["release_signal"])
        if (driver.wait_container(client_id, 10) != 0
                or driver.wait_container(gateway_id, 10) != 0
                or driver.logs(client_id) != "MARKER_MATCH\n"):
            raise InertPeerProbeDenied("marker or exit denied")
        return {"decision": "INERT_PEER_OBSERVED_ONLY",
                "network_id": network_id, "gateway_id": gateway_id,
                "client_id": client_id, "socket_peer": accepted["peer"],
                "peer_qualified": False, "production_ready": False}
    finally:
        for container_id in (client_id, gateway_id):
            if type(container_id) is str and container_id:
                try:
                    driver.remove_container(container_id)
                except Exception as exc:
                    cleanup_errors.append(exc)
        if type(network_id) is str and network_id:
            try:
                driver.remove_network(network_id)
            except Exception as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise InertPeerProbeDenied("exact-object cleanup failed") from cleanup_errors[0]
