"""Source-only plan tests; no Docker objects are created."""

import ast
import hashlib
import inspect

import pytest

from tools.hermes_core import kilo_fake_gateway_probe_plan as subject


RUN_ID = "a" * 32


def test_exact_two_image_private_probe_plan_has_no_authority():
    plan = subject.build_fake_gateway_probe_plan(RUN_ID)
    assert plan["gateway_image"] == subject.GATEWAY_IMAGE
    assert plan["gateway_platform_manifest"] == subject.GATEWAY_PLATFORM_MANIFEST
    assert plan["client_image"] == subject.CLIENT_IMAGE
    assert "--internal" in plan["network_create"]
    for command in (plan["gateway_create"], plan["client_create"]):
        assert command[:3] == ["docker", "container", "create"]
        assert command[command.index("--pull") + 1] == "never"
        assert command[command.index("--platform") + 1] == "linux/amd64"
        assert "--read-only" in command
        assert "--cap-drop" in command
        assert "--publish" not in command and "-p" not in command
        assert "--mount" not in command and "--volume" not in command
    assert plan["gateway_create"][-1] == subject.GATEWAY_IMAGE
    assert plan["client_create"][-3:] == [subject.CLIENT_IMAGE, "-e", subject.CLIENT_SCRIPT]
    assert plan["expected_event"] == {
        "event": "FAKE_REQUEST_PENDING", "body_bytes": len(subject.BODY),
        "body_sha256": hashlib.sha256(subject.BODY).hexdigest(),
    }
    assert plan["probe_authorized"] is False
    assert plan["receiver_executed"] is False
    assert plan["model_invoked"] is False
    assert plan["production_ready"] is False


@pytest.mark.parametrize("run_id", [None, "A" * 32, "a" * 31, "a" * 33,
                                       "a" * 31 + "/", True])
def test_noncanonical_run_identity_denied(run_id):
    with pytest.raises(ValueError, match="run identity denied"):
        subject.build_fake_gateway_probe_plan(run_id)


def test_no_runtime_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"subprocess", "socket", "requests", "os"})
