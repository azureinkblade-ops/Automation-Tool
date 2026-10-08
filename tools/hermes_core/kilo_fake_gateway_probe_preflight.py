"""Read-only image and name admission for the inert fake-gateway probe."""

from tools.hermes_core.kilo_fake_gateway_probe_plan import (
    CLIENT_IMAGE,
    CLIENT_PLATFORM_CONFIG,
    GATEWAY_IMAGE,
    GATEWAY_PLATFORM_MANIFEST,
    build_fake_gateway_probe_plan,
)


class FakeGatewayPreflightDenied(ValueError):
    pass


def inspect_fake_gateway_preflight(plan, gateway_image, client_image,
                                   network_names, container_names):
    """Compare supplied inspect records only; never create Docker objects."""
    if not all(type(value) is dict for value in (plan, gateway_image, client_image)):
        raise FakeGatewayPreflightDenied("image or plan unavailable")
    try:
        canonical = build_fake_gateway_probe_plan(plan.get("run_id"))
    except ValueError as exc:
        raise FakeGatewayPreflightDenied("probe plan denied") from exc
    if plan != canonical:
        raise FakeGatewayPreflightDenied("probe plan denied")
    gateway_config = gateway_image.get("Config")
    client_config = client_image.get("Config")
    if (gateway_image.get("Id") != GATEWAY_PLATFORM_MANIFEST
            or gateway_image.get("Os") != "linux"
            or gateway_image.get("Architecture") != "amd64"
            or GATEWAY_IMAGE not in gateway_image.get("RepoDigests", [])
            or type(gateway_config) is not dict
            or gateway_config.get("User") != "node"
            or gateway_config.get("Entrypoint")
            != ["node", "/opt/ea4e-fake-gateway/gateway.js"]
            or gateway_config.get("WorkingDir") != "/opt/ea4e-fake-gateway"
            or client_image.get("Id") != CLIENT_PLATFORM_CONFIG
            or client_image.get("Os") != "linux"
            or client_image.get("Architecture") != "amd64"
            or not any(type(digest) is str and digest.endswith("@" + CLIENT_IMAGE)
                       for digest in client_image.get("RepoDigests", []))
            or type(client_config) is not dict
            or client_config.get("User") != "node"
            or client_config.get("Entrypoint")
            != ["node", "/opt/ea4e-peer/marker.js"]):
        raise FakeGatewayPreflightDenied("image identity denied")
    if (type(network_names) is not list or type(container_names) is not list
            or not all(type(name) is str for name in network_names + container_names)
            or plan["network_name"] in network_names
            or plan["gateway_name"] in container_names
            or plan["client_name"] in container_names):
        raise FakeGatewayPreflightDenied("probe name collision denied")
    return {"decision": "FAKE_IMAGE_PREFLIGHT_ONLY", "probe_authorized": False,
            "objects_created": False, "production_ready": False}
