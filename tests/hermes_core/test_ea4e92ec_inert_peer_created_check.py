"""Synthetic Docker inspect records; no daemon or container launch."""

import ast
import copy
import inspect

import pytest

from tools.hermes_core import inert_peer_created_check as subject
from tools.hermes_core.inert_peer_probe_plan import build_inert_peer_probe_plan


def records():
    plan = build_inert_peer_probe_plan("a" * 32)
    image = {
        "Id": plan["image_id"], "Os": "linux", "Architecture": "amd64",
        "Config": {"User": "node", "Entrypoint": ["node", "/opt/ea4e-peer/marker.js"],
                   "WorkingDir": "/opt/ea4e-peer", "Env": ["PATH=/bin"],
                   "ExposedPorts": {"3080/tcp": {}}},
    }
    network = {
        "Id": "network-id", "Name": plan["network_name"], "Driver": "bridge",
        "Internal": True, "Labels": {"hermes.ea4e.run": plan["run_id"]},
        "Containers": {},
    }

    def container(name, mode, container_id):
        return {
            "Id": container_id, "Name": "/" + name, "Image": plan["image_id"],
            "State": {"Status": "created", "Running": False},
            "Config": {"Image": plan["image_id"], "User": "node",
                       "Entrypoint": ["node", "/opt/ea4e-peer/marker.js"],
                       "Cmd": [mode], "WorkingDir": "/opt/ea4e-peer",
                       "Env": list(image["Config"]["Env"]),
                       "ExposedPorts": dict(image["Config"]["ExposedPorts"]),
                       "Labels": {"hermes.ea4e.run": plan["run_id"]}},
            "HostConfig": {"NetworkMode": plan["network_name"],
                           "ReadonlyRootfs": True, "Privileged": False,
                           "CapDrop": ["ALL"],
                           "SecurityOpt": ["no-new-privileges:true"],
                           "PidsLimit": 32, "Memory": 268435456,
                           "NanoCpus": 250000000, "PublishAllPorts": False,
                           "PortBindings": {},
                           "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
                           "AutoRemove": False, "Binds": None,
                           "CapAdd": None, "Devices": None},
            "Mounts": [],
            "NetworkSettings": {"Networks": {plan["network_name"]: {
                "NetworkID": network["Id"],
                "Aliases": ["ea4e-peer-gateway"] if mode == "gateway" else [],
            }}},
        }

    return {"plan": plan, "image": image, "network": network,
            "gateway": container(plan["gateway_name"], "gateway", "gateway-id"),
            "client": container(plan["client_name"], "client", "client-id")}


def test_created_metadata_match_is_not_start_authority():
    assert subject.inspect_inert_peer_created(**records()) == {
        "decision": "CREATED_METADATA_MATCH_ONLY",
        "start_authorized": False, "peer_qualified": False,
    }


@pytest.mark.parametrize("change", [
    lambda v: v["network"].update(Internal=False),
    lambda v: v["network"].update(Driver="overlay"),
    lambda v: v["network"].update(Containers={"foreign": {}}),
    lambda v: v["gateway"]["State"].update(Running=True),
    lambda v: v["client"]["Config"].update(Cmd=["backend"]),
    lambda v: v["gateway"]["Config"]["Env"].append("TOKEN=secret"),
    lambda v: v["gateway"]["HostConfig"].update(Privileged=True),
    lambda v: v["client"]["HostConfig"].update(ReadonlyRootfs=False),
    lambda v: v["gateway"]["HostConfig"].update(PortBindings={"3080/tcp": [{}]}),
    lambda v: v["client"]["HostConfig"].update(Binds=["C:\\:/host"]),
    lambda v: v["client"]["HostConfig"].update(DeviceRequests=[{"Driver": "nvidia"}]),
    lambda v: v["client"]["HostConfig"].update(ExtraHosts=["host.docker.internal:host-gateway"]),
    lambda v: v["gateway"].update(Mounts=[{"Type": "bind"}]),
    lambda v: v["gateway"]["HostConfig"].update(NetworkMode="bridge"),
    lambda v: v["client"]["NetworkSettings"]["Networks"].update(extra={}),
    lambda v: v["gateway"]["NetworkSettings"]["Networks"][v["plan"]["network_name"]].update(Aliases=[]),
    lambda v: v["client"].update(Id="gateway-id"),
    lambda v: v["plan"].update(probe_authorized=True),
], ids=["external-network", "wrong-driver", "foreign-member", "running",
        "wrong-command", "extra-env", "privileged", "writable-root",
        "published-port", "bind-mount", "gpu-request", "extra-host", "mount", "wrong-network",
        "second-network", "missing-alias", "duplicate-id", "forged-plan"])
def test_created_metadata_denies_drift(change):
    values = copy.deepcopy(records())
    change(values)
    with pytest.raises(subject.InertPeerCreatedDenied):
        subject.inspect_inert_peer_created(**values)


def test_created_check_has_no_runtime_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports == {"tools.hermes_core.inert_peer_probe_preflight"}
