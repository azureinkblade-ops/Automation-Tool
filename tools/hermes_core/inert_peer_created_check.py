"""Pure prestart check for the proposed inert Docker peer probe."""

from tools.hermes_core.inert_peer_probe_preflight import (
    InertPeerPreflightDenied,
    inspect_inert_peer_preflight,
)


class InertPeerCreatedDenied(ValueError):
    pass


def inspect_inert_peer_created(plan: dict, image: dict, network: dict,
                               gateway: dict, client: dict) -> dict:
    """Compare inspect records only; a match never authorizes start."""
    try:
        inspect_inert_peer_preflight(plan, image, [], [])
    except InertPeerPreflightDenied as exc:
        raise InertPeerCreatedDenied("plan or image denied") from exc
    if not all(type(item) is dict for item in (network, gateway, client)):
        raise InertPeerCreatedDenied("missing inspect record")
    label = {"hermes.ea4e.run": plan["run_id"]}
    if (type(network.get("Id")) is not str or not network["Id"]
            or network.get("Name") != plan["network_name"]
            or network.get("Driver") != "bridge"
            or network.get("Internal") is not True
            or network.get("Labels") != label):
        raise InertPeerCreatedDenied("network identity denied")
    members = network.get("Containers")
    if type(members) is not dict:
        raise InertPeerCreatedDenied("network membership unavailable")

    ids = []
    for container, name, mode in ((gateway, plan["gateway_name"], "gateway"),
                                  (client, plan["client_name"], "client")):
        container_id = container.get("Id")
        config = container.get("Config")
        host = container.get("HostConfig")
        state = container.get("State")
        settings = container.get("NetworkSettings")
        if (type(container_id) is not str or not container_id
                or container.get("Name") != "/" + name
                or container.get("Image") != plan["image_id"]
                or type(config) is not dict or type(host) is not dict
                or type(state) is not dict or type(settings) is not dict):
            raise InertPeerCreatedDenied("container identity denied")
        if (state.get("Status") != "created" or state.get("Running") is not False
                or config.get("Image") != plan["image_id"]
                or config.get("User") != "node"
                or config.get("Entrypoint") != ["node", "/opt/ea4e-peer/marker.js"]
                or config.get("Cmd") != [mode]
                or config.get("WorkingDir") != "/opt/ea4e-peer"
                or config.get("Env") != image["Config"].get("Env")
                or config.get("ExposedPorts") != image["Config"].get("ExposedPorts")
                or config.get("Labels") != label):
            raise InertPeerCreatedDenied("container config denied")
        if (host.get("NetworkMode") != plan["network_name"]
                or host.get("ReadonlyRootfs") is not True
                or host.get("Privileged") is not False
                or host.get("CapDrop") != ["ALL"]
                or host.get("SecurityOpt") != ["no-new-privileges:true"]
                or host.get("PidsLimit") != 32
                or host.get("Memory") != 268435456
                or host.get("NanoCpus") != 250000000
                or host.get("PublishAllPorts") is not False
                or host.get("PortBindings") not in (None, {})
                or host.get("RestartPolicy") != {"Name": "no", "MaximumRetryCount": 0}
                or host.get("AutoRemove") is not False
                or host.get("Binds") not in (None, [])
                or host.get("CapAdd") not in (None, [])
                or host.get("Devices") not in (None, [])
                or host.get("DeviceRequests") not in (None, [])
                or host.get("VolumesFrom") not in (None, [])
                or host.get("ExtraHosts") not in (None, [])
                or host.get("Links") not in (None, [])
                or container.get("Mounts") != []):
            raise InertPeerCreatedDenied("container host policy denied")
        networks = settings.get("Networks")
        if type(networks) is not dict or set(networks) != {plan["network_name"]}:
            raise InertPeerCreatedDenied(f"{mode} network attachment set denied")
        endpoint = networks[plan["network_name"]]
        if type(endpoint) is not dict:
            raise InertPeerCreatedDenied(f"{mode} endpoint shape denied")
        # Docker may leave NetworkID empty until start; the running check binds it.
        if endpoint.get("NetworkID") not in ("", network["Id"]):
            raise InertPeerCreatedDenied(f"{mode} endpoint network ID denied")
        if mode == "gateway" and "ea4e-peer-gateway" not in (
                endpoint.get("Aliases") or []):
            raise InertPeerCreatedDenied("gateway alias denied")
        ids.append(container_id)
    if ids[0] == ids[1] or not set(members).issubset(set(ids)):
        raise InertPeerCreatedDenied("network membership denied")
    return {"decision": "CREATED_METADATA_MATCH_ONLY",
            "start_authorized": False, "peer_qualified": False}
