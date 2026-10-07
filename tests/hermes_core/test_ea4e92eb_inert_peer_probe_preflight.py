"""Synthetic Docker metadata only; no daemon call."""

import ast
import copy
import inspect

import pytest

from tools.hermes_core import inert_peer_probe_preflight as subject
from tools.hermes_core.inert_peer_probe_plan import build_inert_peer_probe_plan, IMAGE_ID


def fixture():
    return {
        "plan": build_inert_peer_probe_plan("a" * 32),
        "image": {
            "Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64",
            "Config": {"User": "node",
                       "Entrypoint": ["node", "/opt/ea4e-peer/marker.js"],
                       "WorkingDir": "/opt/ea4e-peer"},
        },
        "network_names": [],
        "container_names": [],
    }


def test_exact_metadata_and_empty_names_are_read_only_candidate():
    assert subject.inspect_inert_peer_preflight(**fixture()) == {
        "decision": "READ_ONLY_PREFLIGHT_MATCH",
        "probe_authorized": False,
        "docker_objects_created": False,
    }


@pytest.mark.parametrize("change", [
    lambda v: v["image"].update(Id="sha256:" + "0" * 64),
    lambda v: v["image"].update(Os="windows"),
    lambda v: v["image"].update(Architecture="arm64"),
    lambda v: v["image"]["Config"].update(User="root"),
    lambda v: v["image"]["Config"].update(Entrypoint=["npm", "run", "backend"]),
    lambda v: v["image"]["Config"].update(WorkingDir="/app"),
    lambda v: v["plan"].update(probe_authorized=True),
    lambda v: v["plan"].update(image_id="sha256:" + "0" * 64),
    lambda v: v["plan"]["gateway_create"].append("--publish"),
    lambda v: v["network_names"].append(v["plan"]["network_name"]),
    lambda v: v["container_names"].append(v["plan"]["gateway_name"]),
    lambda v: v["container_names"].append(v["plan"]["client_name"]),
], ids=["wrong-image", "wrong-os", "wrong-arch", "root", "app-entrypoint",
        "wrong-workdir", "forged-authorization", "plan-image-drift",
        "plan-command-drift",
        "network-collision", "gateway-collision", "client-collision"])
def test_mismatches_denied(change):
    values = copy.deepcopy(fixture())
    change(values)
    with pytest.raises(subject.InertPeerPreflightDenied):
        subject.inspect_inert_peer_preflight(**values)


def test_preflight_has_no_runtime_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports == {"tools.hermes_core.inert_peer_probe_plan"}
