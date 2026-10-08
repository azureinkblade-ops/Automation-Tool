"""Diagnostic-only created metadata sequence over an injected driver."""

import re

from tools.hermes_core.kilo_fake_gateway_probe_created import inspect_fake_gateway_created
from tools.hermes_core.kilo_fake_gateway_probe_plan import build_fake_gateway_probe_plan
from tools.hermes_core.kilo_fake_gateway_probe_preflight import inspect_fake_gateway_preflight


class FakeCreatedDiagnosticDenied(RuntimeError):
    pass


def run_fake_created_diagnostic(driver, run_id):
    """Inspect never-started objects and clean exact IDs; no start capability."""
    plan = build_fake_gateway_probe_plan(run_id)
    gateway_image = driver.inspect_image(plan["gateway_image"])
    client_image = driver.inspect_image(plan["client_image"])
    inspect_fake_gateway_preflight(plan, gateway_image, client_image,
                                   driver.network_names(), driver.container_names())
    network_id = gateway_id = client_id = None
    try:
        network_id = driver.create_network(plan["network_create"])
        gateway_id = driver.create_container(plan["gateway_create"])
        client_id = driver.create_container(plan["client_create"])
        identities = (network_id, gateway_id, client_id)
        if (any(type(identity) is not str
                or re.fullmatch(r"[0-9a-f]{64}", identity) is None
                for identity in identities)
                or len(set(identities)) != 3):
            raise FakeCreatedDiagnosticDenied("created identity denied")
        network = driver.inspect_network(network_id)
        gateway = driver.inspect_container(gateway_id)
        client = driver.inspect_container(client_id)
        if (network.get("Id") != network_id
                or gateway.get("Id") != gateway_id
                or client.get("Id") != client_id):
            raise FakeCreatedDiagnosticDenied("inspect identity denied")
        inspect_fake_gateway_created(plan, gateway_image, client_image,
                                     network, gateway, client)
        return {"decision": "FAKE_CREATED_DIAGNOSTIC_ONLY",
                "network_id": network_id, "gateway_id": gateway_id,
                "client_id": client_id, "containers_started": 0,
                "peer_qualified": False, "production_ready": False}
    finally:
        try:
            cleanup = driver.cleanup_owned(plan, network_id, gateway_id, client_id)
        except Exception as exc:
            raise FakeCreatedDiagnosticDenied("owned-object cleanup failed") from exc
        if cleanup != {"remaining_network_ids": [],
                       "remaining_container_ids": []}:
            raise FakeCreatedDiagnosticDenied("owned-object cleanup unconfirmed")
