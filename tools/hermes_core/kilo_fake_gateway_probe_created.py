"""Pure created-container admission for the inert fake-gateway probe."""

from tools.hermes_core.kilo_fake_gateway_probe_preflight import (
    FakeGatewayPreflightDenied,
    inspect_fake_gateway_preflight,
)


class FakeGatewayCreatedDenied(ValueError):
    pass


def inspect_fake_gateway_created(plan, gateway_image, client_image,
                                 network, gateway, client):
    """Compare supplied prestart records only; a match does not allow start."""
    try:
        inspect_fake_gateway_preflight(plan, gateway_image, client_image, [], [])
    except FakeGatewayPreflightDenied as exc:
        raise FakeGatewayCreatedDenied("plan or image denied") from exc
    if not all(type(record) is dict for record in (network, gateway, client)):
        raise FakeGatewayCreatedDenied("created record unavailable")
    network_id = network.get("Id")
    label = {"hermes.ea4e.run": plan["run_id"]}
    if (type(network_id) is not str or not network_id
            or network.get("Name") != plan["network_name"]
            or network.get("Driver") != "bridge"
            or network.get("Internal") is not True
            or network.get("EnableIPv6") is not False
            or network.get("Labels") != label
            or type(network.get("Containers")) is not dict):
        raise FakeGatewayCreatedDenied("created network denied")

    identities = []
    for role, container, image in (("gateway", gateway, gateway_image),
                                   ("client", client, client_image)):
        identity = container.get("Id")
        config = container.get("Config")
        host = container.get("HostConfig")
        state = container.get("State")
        settings = container.get("NetworkSettings")
        if type(identity) is not str or not identity:
            raise FakeGatewayCreatedDenied(role + " returned ID denied")
        if container.get("Name") != "/" + plan[role + "_name"]:
            raise FakeGatewayCreatedDenied(role + " name denied")
        if container.get("Image") != image["Id"]:
            observed = container.get("Image")
            suffix = (" (observed " + observed + ")"
                      if type(observed) is str
                      and observed.startswith("sha256:")
                      and len(observed) == 71
                      and all(char in "0123456789abcdef"
                              for char in observed[7:]) else "")
            raise FakeGatewayCreatedDenied(role + " image ID denied" + suffix)
        if not all(type(item) is dict for item in
                   (config, host, state, settings)):
            raise FakeGatewayCreatedDenied(role + " record shape denied")
        expected_entry = (image["Config"]["Entrypoint"] if role == "gateway"
                          else ["node"])
        expected_cmd = (None if role == "gateway"
                        else ["-e", plan["client_create"][-1]])
        if (state.get("Status") != "created" or state.get("Running") is not False
                or config.get("Image") != plan[role + "_image"]
                or config.get("User") != "node"
                or config.get("Entrypoint") != expected_entry
                or config.get("Cmd") != expected_cmd
                or config.get("Env") != image["Config"].get("Env")
                or config.get("WorkingDir") != image["Config"].get("WorkingDir")
                or config.get("ExposedPorts") != image["Config"].get("ExposedPorts")
                or config.get("Labels") != label):
            raise FakeGatewayCreatedDenied(role + " config denied")
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
                or host.get("Devices") not in (None, [])
                or host.get("DeviceRequests") not in (None, [])
                or host.get("VolumesFrom") not in (None, [])
                or host.get("ExtraHosts") not in (None, [])
                or host.get("Links") not in (None, [])
                or container.get("Mounts") != []):
            raise FakeGatewayCreatedDenied(role + " host policy denied")
        attachments = settings.get("Networks")
        ports = settings.get("Ports")
        if (type(attachments) is not dict
                or set(attachments) != {plan["network_name"]}
                or type(attachments[plan["network_name"]]) is not dict
                or attachments[plan["network_name"]].get("NetworkID")
                not in ("", network_id)
                or type(ports) is not dict
                or any(value is not None for value in ports.values())):
            raise FakeGatewayCreatedDenied(role + " prestart network denied")
        if (role == "gateway" and "ea4e-fake-gateway" not in
                (attachments[plan["network_name"]].get("Aliases") or [])):
            raise FakeGatewayCreatedDenied("gateway alias denied")
        identities.append(identity)
    if (identities[0] == identities[1]
            or not set(network["Containers"]).issubset(set(identities))):
        raise FakeGatewayCreatedDenied("created membership denied")
    return {"decision": "FAKE_CREATED_METADATA_MATCH_ONLY",
            "start_authorized": False, "peer_qualified": False,
            "production_ready": False}
