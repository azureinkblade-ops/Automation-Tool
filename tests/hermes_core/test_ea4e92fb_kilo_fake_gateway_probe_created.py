"""Created-state fake records only; no Docker call or container start."""

from copy import deepcopy

import pytest

from tools.hermes_core.kilo_fake_gateway_probe_created import (
    FakeGatewayCreatedDenied,
    inspect_fake_gateway_created,
)
from tools.hermes_core.kilo_fake_gateway_probe_plan import (
    CLIENT_IMAGE, CLIENT_PLATFORM_CONFIG, GATEWAY_IMAGE,
    GATEWAY_PLATFORM_MANIFEST, build_fake_gateway_probe_plan,
)


def records():
    plan = build_fake_gateway_probe_plan("a" * 32)
    common = {"Env": ["PATH=/bin"], "ExposedPorts": {"3080/tcp": {}}}
    images = []
    for identity, ref, entry, workdir in (
            (GATEWAY_PLATFORM_MANIFEST, GATEWAY_IMAGE,
             ["node", "/opt/ea4e-fake-gateway/gateway.js"],
             "/opt/ea4e-fake-gateway"),
            (CLIENT_PLATFORM_CONFIG, "hermes/ea4e-peer-helper@" + CLIENT_IMAGE,
             ["node", "/opt/ea4e-peer/marker.js"], "/opt/ea4e-peer")):
        images.append({"Id": identity, "Os": "linux", "Architecture": "amd64",
                       "RepoDigests": [ref], "Config": {
                           **common, "User": "node", "Entrypoint": entry,
                           "WorkingDir": workdir}})
    network = {"Id": "network-id", "Name": plan["network_name"],
               "Driver": "bridge", "Internal": True, "EnableIPv6": False,
               "Labels": {"hermes.ea4e.run": plan["run_id"]},
               "Containers": {}}
    containers = []
    for role, image in zip(("gateway", "client"), images):
        containers.append({
            "Id": role + "-id", "Name": "/" + plan[role + "_name"],
            "Image": image["Id"], "State": {"Status": "created", "Running": False},
            "Config": {"Image": plan[role + "_image"], "User": "node",
                       "Entrypoint": image["Config"]["Entrypoint"]
                       if role == "gateway" else ["node"],
                       "Cmd": None if role == "gateway" else
                       ["-e", plan["client_create"][-1]],
                       "Env": image["Config"]["Env"],
                       "WorkingDir": image["Config"]["WorkingDir"],
                       "ExposedPorts": image["Config"]["ExposedPorts"],
                       "Labels": {"hermes.ea4e.run": plan["run_id"]}},
            "HostConfig": {"NetworkMode": plan["network_name"],
                           "ReadonlyRootfs": True, "Privileged": False,
                           "CapDrop": ["ALL"],
                           "SecurityOpt": ["no-new-privileges:true"],
                           "PidsLimit": 32, "Memory": 268435456,
                           "NanoCpus": 250000000,
                           "PublishAllPorts": False, "PortBindings": {},
                           "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
                           "AutoRemove": False, "Binds": None,
                           "Devices": None, "DeviceRequests": None,
                           "VolumesFrom": None, "ExtraHosts": None, "Links": None},
            "Mounts": [],
            "NetworkSettings": {"Networks": {plan["network_name"]: {
                "NetworkID": "", "Aliases": ["ea4e-fake-gateway"]
                if role == "gateway" else []}},
                "Ports": {"3080/tcp": None}},
        })
    return plan, images[0], images[1], network, containers[0], containers[1]


def test_exact_created_records_are_not_start_authority():
    assert inspect_fake_gateway_created(*records()) == {
        "decision": "FAKE_CREATED_METADATA_MATCH_ONLY",
        "start_authorized": False, "peer_qualified": False,
        "production_ready": False,
    }


@pytest.mark.parametrize("index,path,value", [
    (4, ("Image",), "wrong"),
    (5, ("Config", "Cmd"), ["-e", "wrong"]),
    (4, ("HostConfig", "Privileged"), True),
    (5, ("HostConfig", "PortBindings"), {"8181/tcp": [{}]}),
    (4, ("Mounts",), [{}]),
    (5, ("NetworkSettings", "Networks"), {}),
    (4, ("NetworkSettings", "Networks", "NETWORK", "NetworkID"), "wrong"),
    (3, ("EnableIPv6",), True),
])
def test_drift_denies_without_start_authority(index, path, value):
    values = list(deepcopy(records()))
    target = values[index]
    if "NETWORK" in path:
        path = tuple(values[0]["network_name"] if part == "NETWORK" else part
                     for part in path)
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(FakeGatewayCreatedDenied):
        inspect_fake_gateway_created(*values)
