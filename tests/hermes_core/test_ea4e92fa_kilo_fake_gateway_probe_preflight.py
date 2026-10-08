"""Fake image/name preflight tests; no Docker daemon access."""

from copy import deepcopy

import pytest

from tools.hermes_core.kilo_fake_gateway_probe_plan import (
    CLIENT_IMAGE,
    CLIENT_PLATFORM_CONFIG,
    GATEWAY_IMAGE,
    GATEWAY_PLATFORM_MANIFEST,
    build_fake_gateway_probe_plan,
)
from tools.hermes_core.kilo_fake_gateway_probe_preflight import (
    FakeGatewayPreflightDenied,
    inspect_fake_gateway_preflight,
)


def records():
    plan = build_fake_gateway_probe_plan("a" * 32)
    gateway = {"Id": GATEWAY_PLATFORM_MANIFEST, "Os": "linux",
               "Architecture": "amd64", "RepoDigests": [GATEWAY_IMAGE],
               "Config": {"User": "node", "Entrypoint": [
                   "node", "/opt/ea4e-fake-gateway/gateway.js"],
                   "WorkingDir": "/opt/ea4e-fake-gateway"}}
    client = {"Id": CLIENT_PLATFORM_CONFIG, "Os": "linux",
              "Architecture": "amd64",
              "RepoDigests": ["hermes/ea4e-peer-helper@" + CLIENT_IMAGE],
              "Config": {"User": "node", "Entrypoint": [
                  "node", "/opt/ea4e-peer/marker.js"]}}
    return plan, gateway, client


def test_exact_images_and_free_names_are_preflight_only():
    plan, gateway, client = records()
    assert inspect_fake_gateway_preflight(plan, gateway, client, [], []) == {
        "decision": "FAKE_IMAGE_PREFLIGHT_ONLY", "probe_authorized": False,
        "objects_created": False, "production_ready": False,
    }


@pytest.mark.parametrize("target,key,value", [
    ("gateway", "Id", "sha256:" + "0" * 64),
    ("gateway", "RepoDigests", []),
    ("gateway", "Architecture", "arm64"),
    ("client", "Id", "sha256:" + "0" * 64),
    ("client", "RepoDigests", []),
    ("client", "Os", "windows"),
])
def test_changed_image_identity_denied(target, key, value):
    plan, gateway, client = records()
    mutated = deepcopy(gateway if target == "gateway" else client)
    mutated[key] = value
    with pytest.raises(FakeGatewayPreflightDenied):
        inspect_fake_gateway_preflight(plan, mutated if target == "gateway" else gateway,
                                       mutated if target == "client" else client, [], [])


def test_changed_entrypoint_or_plan_denied():
    plan, gateway, client = records()
    gateway["Config"]["Entrypoint"] = ["node", "other.js"]
    with pytest.raises(FakeGatewayPreflightDenied):
        inspect_fake_gateway_preflight(plan, gateway, client, [], [])
    plan, gateway, client = records()
    plan["client_image"] = "other"
    with pytest.raises(FakeGatewayPreflightDenied):
        inspect_fake_gateway_preflight(plan, gateway, client, [], [])


@pytest.mark.parametrize("kind", ["network", "gateway", "client"])
def test_existing_name_denies_before_creation(kind):
    plan, gateway, client = records()
    networks = [plan["network_name"]] if kind == "network" else []
    containers = [plan[kind + "_name"]] if kind != "network" else []
    with pytest.raises(FakeGatewayPreflightDenied):
        inspect_fake_gateway_preflight(plan, gateway, client,
                                       networks, containers)
