"""Pure 92EB image/name preflight; never creates or starts Docker objects."""

from tools.hermes_core.inert_peer_probe_plan import build_inert_peer_probe_plan, IMAGE_ID


class InertPeerPreflightDenied(ValueError):
    pass


def inspect_inert_peer_preflight(plan: dict, image: dict,
                                network_names: list[str],
                                container_names: list[str]) -> dict:
    if not all(type(value) is dict for value in (plan, image)):
        raise InertPeerPreflightDenied("missing plan or image")
    try:
        canonical = build_inert_peer_probe_plan(plan.get("run_id"))
    except ValueError as exc:
        raise InertPeerPreflightDenied("invalid plan identity") from exc
    if plan != canonical:
        raise InertPeerPreflightDenied("plan identity or authority denied")
    config = image.get("Config")
    if (image.get("Id") != IMAGE_ID
            or image.get("Os") != "linux"
            or image.get("Architecture") != "amd64"
            or type(config) is not dict
            or config.get("User") != "node"
            or config.get("Entrypoint") != ["node", "/opt/ea4e-peer/marker.js"]
            or config.get("WorkingDir") != "/opt/ea4e-peer"):
        raise InertPeerPreflightDenied("helper image metadata denied")
    if (type(network_names) is not list or type(container_names) is not list
            or not all(type(name) is str for name in network_names + container_names)):
        raise InertPeerPreflightDenied("invalid name inventory")
    if (plan.get("network_name") in network_names
            or plan.get("gateway_name") in container_names
            or plan.get("client_name") in container_names):
        raise InertPeerPreflightDenied("probe identity already exists")
    return {"decision": "READ_ONLY_PREFLIGHT_MATCH",
            "probe_authorized": False, "docker_objects_created": False}
