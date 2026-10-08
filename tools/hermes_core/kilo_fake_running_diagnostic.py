"""Fake-driver-only ordering for an inert pending-request observation."""

import re

from tools.hermes_core.kilo_fake_gateway_probe_created import inspect_fake_gateway_created
from tools.hermes_core.kilo_fake_gateway_probe_plan import build_fake_gateway_probe_plan
from tools.hermes_core.kilo_fake_gateway_probe_preflight import inspect_fake_gateway_preflight
from tools.hermes_core.kilo_fake_gateway_running import inspect_fake_gateway_running
from tools.hermes_core.kilo_fake_pending_event import parse_fake_pending_event


class FakeRunningDiagnosticDenied(RuntimeError):
    pass


def _snapshot(driver, network_id, gateway_id, client_id):
    records = (driver.inspect_network(network_id),
               driver.inspect_container(gateway_id),
               driver.inspect_container(client_id))
    if (any(type(record) is not dict for record in records)
            or tuple(record.get("Id") for record in records)
            != (network_id, gateway_id, client_id)):
        raise FakeRunningDiagnosticDenied("snapshot identity denied")
    return records


def run_fake_running_diagnostic(driver, run_id):
    """Require created and two fresh running matches; never release a request."""
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
            raise FakeRunningDiagnosticDenied("created identity denied")
        created = _snapshot(driver, *identities)
        inspect_fake_gateway_created(plan, gateway_image, client_image, *created)
        driver.start_container(gateway_id)
        driver.start_container(client_id)
        event = parse_fake_pending_event(driver.pending_line(gateway_id, 10))
        for _ in range(2):
            running = _snapshot(driver, *identities)
            inspect_fake_gateway_running(plan, event, *running)
        return {"decision": "FAKE_RUNNING_DIAGNOSTIC_ONLY",
                "running_matches": 2, "release_signals": 0,
                "peer_qualified": False, "production_ready": False}
    finally:
        try:
            cleanup = driver.cleanup_running_owned(plan, network_id,
                                                   gateway_id, client_id)
        except Exception as exc:
            raise FakeRunningDiagnosticDenied("owned-object cleanup failed") from exc
        if cleanup != {"remaining_network_ids": [],
                       "remaining_container_ids": []}:
            raise FakeRunningDiagnosticDenied("owned-object cleanup unconfirmed")
