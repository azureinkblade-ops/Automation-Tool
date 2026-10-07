"""Pure command-envelope tests; no Docker CLI invocation."""

import ast
import inspect

import pytest

from tools.hermes_core import inert_peer_probe_plan as subject


RUN_ID = "a" * 32


def test_fixed_inert_plan_has_no_execution_authority():
    plan = subject.build_inert_peer_probe_plan(RUN_ID)
    assert plan == subject.build_inert_peer_probe_plan(RUN_ID)
    assert plan["image_id"] == subject.IMAGE_ID
    assert plan["probe_authorized"] is False
    assert plan["kilo_receiver_executed"] is False
    assert plan["model_invoked"] is False
    assert plan["production_ready"] is False
    assert plan["max_containers"] == 2
    assert plan["max_networks"] == 1
    assert plan["timeout_seconds"] == 30


def test_network_and_container_commands_are_bounded():
    plan = subject.build_inert_peer_probe_plan(RUN_ID)
    network = plan["network_create"]
    assert network[:3] == ["docker", "network", "create"]
    assert "--internal" in network
    assert network[-1] == plan["network_name"]
    assert plan["start_order"] == [plan["gateway_name"], plan["client_name"]]
    for field, name, mode in (("gateway_create", plan["gateway_name"], "gateway"),
                              ("client_create", plan["client_name"], "client")):
        argv = plan[field]
        assert argv[:5] == ["docker", "container", "create", "--name", name]
        assert argv[-2:] == [subject.IMAGE_ID, mode]
        assert ("--network-alias" in argv) is (mode == "gateway")
        if mode == "gateway":
            assert argv[argv.index("--network-alias") + 1] == "ea4e-peer-gateway"
        for flag in ("--network", "--user", "--read-only", "--cap-drop",
                     "--security-opt", "--pids-limit", "--memory", "--cpus",
                     "--pull", "--platform", "--restart"):
            assert flag in argv
        assert argv[argv.index("--pull") + 1] == "never"
        assert argv[argv.index("--platform") + 1] == "linux/amd64"
        assert not any(flag in argv for flag in
                       ("--publish", "-p", "--volume", "-v", "--mount",
                        "--privileged", "--network-host"))
    assert plan["expected_request"] == {"method": "GET", "path": "/marker", "count": 1}
    assert "exact_created_container_ids" in plan["cleanup"]


@pytest.mark.parametrize("run_id", ["", "A" * 32, "a" * 31, "g" * 32,
                                     "a" * 32 + " --publish 80:80", None, 123])
def test_untrusted_or_ambiguous_run_ids_denied(run_id):
    with pytest.raises(ValueError):
        subject.build_inert_peer_probe_plan(run_id)


def test_plan_module_has_no_runtime_capability():
    tree = ast.parse(inspect.getsource(subject))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert imports == {"re"}
