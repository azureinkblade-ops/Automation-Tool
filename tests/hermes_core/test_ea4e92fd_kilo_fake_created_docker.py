"""Pinned Docker diagnostic driver with an injected fake CLI only."""

import hashlib
import json
import subprocess

import pytest

from tools.hermes_core.kilo_fake_created_docker import (
    FakeCreatedDockerDenied,
    FakeCreatedDockerDriver,
)
from tools.hermes_core.kilo_fake_gateway_probe_plan import build_fake_gateway_probe_plan


NETWORK_ID = "1" * 64
GATEWAY_ID = "2" * 64
CLIENT_ID = "3" * 64


class FakeCLI:
    def __init__(self, plan, *, lose_client_result=False, wrong_label=False):
        self.plan = plan
        self.calls = []
        self.containers = {}
        self.network = None
        self.lose_client_result = lose_client_result
        self.wrong_label = wrong_label

    def __call__(self, argv):
        args = argv[1:]
        self.calls.append(args)
        label = self.plan["run_id"]
        def result(value="", code=0, error=""):
            return subprocess.CompletedProcess(argv, code, value, error)
        if args == self.plan["network_create"][1:]:
            self.network = {"Id": NETWORK_ID, "Name": self.plan["network_name"],
                            "Labels": {"hermes.ea4e.run": label}, "Containers": {}}
            return result(NETWORK_ID + "\n")
        for role, identity in (("gateway", GATEWAY_ID), ("client", CLIENT_ID)):
            if args == self.plan[role + "_create"][1:]:
                self.containers[role] = {
                    "Id": identity, "Name": "/" + self.plan[role + "_name"],
                    "Config": {"Image": self.plan[role + "_image"],
                               "Labels": {"hermes.ea4e.run": "wrong" if
                                          self.wrong_label and role == "client"
                                          else label}},
                    "State": {"Running": False},
                }
                if role == "client" and self.lose_client_result:
                    return result(code=1, error="response lost")
                return result(identity + "\n")
            if args == ["container", "inspect", self.plan[role + "_name"]]:
                record = self.containers.get(role)
                return result(json.dumps([record]) if record else "", 0 if record else 1,
                              "" if record else "No such container")
            if args == ["container", "rm", "--force", identity]:
                self.containers.pop(role, None)
                return result(identity + "\n")
        if args == ["network", "inspect", self.plan["network_name"]]:
            return result(json.dumps([self.network]) if self.network else "",
                          0 if self.network else 1,
                          "" if self.network else "No such network")
        if args == ["network", "rm", NETWORK_ID]:
            if self.containers:
                return result(code=1, error="network in use")
            self.network = None
            return result(NETWORK_ID + "\n")
        if args[:3] == ["container", "ls", "--all"] and "--filter" in args:
            return result("\n".join(record["Id"][:12] for record in
                                    self.containers.values()))
        if args[:2] == ["network", "ls"] and "--filter" in args:
            return result(NETWORK_ID[:12] if self.network else "")
        return result(code=1, error="unexpected command")


@pytest.fixture
def driver_factory(tmp_path):
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"inert fake executable")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    plan = build_fake_gateway_probe_plan("a" * 32)
    def create(**kwargs):
        cli = FakeCLI(plan, **kwargs)
        driver = FakeCreatedDockerDriver(
            run_id=plan["run_id"], docker_executable=str(executable),
            docker_sha256=digest, run_command=cli)
        return plan, driver, cli, executable
    return create


def test_exact_created_objects_are_removed_by_id(driver_factory):
    plan, driver, cli, _ = driver_factory()
    network_id = driver.create_network(plan["network_create"])
    gateway_id = driver.create_container(plan["gateway_create"])
    client_id = driver.create_container(plan["client_create"])
    assert driver.cleanup_owned(plan, network_id, gateway_id, client_id) == {
        "remaining_network_ids": [], "remaining_container_ids": []}
    assert cli.containers == {} and cli.network is None
    assert cli.calls.index(["container", "rm", "--force", CLIENT_ID]) \
        < cli.calls.index(["network", "rm", NETWORK_ID])


def test_lost_create_response_reconciles_exact_name_and_label(driver_factory):
    plan, driver, cli, _ = driver_factory(lose_client_result=True)
    network_id = driver.create_network(plan["network_create"])
    gateway_id = driver.create_container(plan["gateway_create"])
    with pytest.raises(FakeCreatedDockerDenied):
        driver.create_container(plan["client_create"])
    assert driver.cleanup_owned(plan, network_id, gateway_id, None) == {
        "remaining_network_ids": [], "remaining_container_ids": []}
    assert cli.containers == {} and cli.network is None


def test_mismatched_label_is_not_deleted(driver_factory):
    plan, driver, cli, _ = driver_factory(wrong_label=True)
    network_id = driver.create_network(plan["network_create"])
    gateway_id = driver.create_container(plan["gateway_create"])
    client_id = driver.create_container(plan["client_create"])
    with pytest.raises(FakeCreatedDockerDenied, match="cleanup incomplete"):
        driver.cleanup_owned(plan, network_id, gateway_id, client_id)
    assert "client" in cli.containers
    assert ["container", "rm", "--force", CLIENT_ID] not in cli.calls


def test_executable_drift_denies_before_any_command(driver_factory):
    plan, driver, cli, executable = driver_factory()
    executable.write_bytes(b"changed")
    with pytest.raises(FakeCreatedDockerDenied, match="executable changed"):
        driver.create_network(plan["network_create"])
    assert cli.calls == []


def test_unplanned_create_argv_denied_without_command(driver_factory):
    plan, driver, cli, _ = driver_factory()
    with pytest.raises(FakeCreatedDockerDenied, match="argv denied"):
        driver.create_container(plan["client_create"] + ["other"])
    assert cli.calls == []
