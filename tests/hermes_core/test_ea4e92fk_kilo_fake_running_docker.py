"""Pinned running driver against an injected fake CLI only."""

import hashlib
import json
import subprocess

import pytest

from tools.hermes_core.kilo_fake_gateway_probe_plan import build_fake_gateway_probe_plan
from tools.hermes_core.kilo_fake_running_docker import FakeRunningDockerDriver
from tools.hermes_core.kilo_fake_created_docker import FakeCreatedDockerDenied


NETWORK_ID, GATEWAY_ID, CLIENT_ID = "1" * 64, "2" * 64, "3" * 64


class FakeCLI:
    def __init__(self, plan, *, lose_start=False, lose_client_create=False,
                 wrong_label=False, log_override=None, log_stderr=""):
        self.plan = plan
        self.lose_start = lose_start
        self.lose_client_create = lose_client_create
        self.wrong_label = wrong_label
        self.log_override = log_override
        self.log_stderr = log_stderr
        self.calls = []
        self.network = None
        self.containers = {}

    def __call__(self, argv):
        args = argv[1:]
        self.calls.append(args)
        def result(value="", code=0, error=""):
            return subprocess.CompletedProcess(argv, code, value, error)
        if args == self.plan["network_create"][1:]:
            self.network = {"Id": NETWORK_ID, "Name": self.plan["network_name"],
                            "Labels": {"hermes.ea4e.run": self.plan["run_id"]},
                            "Containers": {}}
            return result(NETWORK_ID + "\n")
        for role, identity in (("gateway", GATEWAY_ID), ("client", CLIENT_ID)):
            if args == self.plan[role + "_create"][1:]:
                self.containers[role] = {
                    "Id": identity, "Name": "/" + self.plan[role + "_name"],
                    "Config": {"Image": self.plan[role + "_image"],
                               "Labels": {"hermes.ea4e.run":
                                          "wrong" if self.wrong_label else
                                          self.plan["run_id"]}},
                    "State": {"Status": "created", "Running": False},
                }
                if role == "client" and self.lose_client_create:
                    return result(code=1, error="response lost")
                return result(identity + "\n")
            if args in (["container", "inspect", identity],
                        ["container", "inspect", self.plan[role + "_name"]]):
                record = self.containers.get(role)
                return result(json.dumps([record]) if record else "",
                              0 if record else 1,
                              "" if record else "No such container")
            if args == ["container", "start", identity]:
                self.containers[role]["State"] = {"Status": "running",
                                                  "Running": True}
                if self.lose_start:
                    return result(code=1, error="response lost")
                return result(identity + "\n")
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
            return result("\n".join(c["Id"][:12] for c in self.containers.values()))
        if args[:2] == ["network", "ls"] and "--filter" in args:
            return result(NETWORK_ID[:12] if self.network else "")
        if args == ["container", "logs", "--tail", "2", GATEWAY_ID]:
            if self.log_override is not None:
                return result(self.log_override, error=self.log_stderr)
            event = {"event": "FAKE_REQUEST_PENDING", "peer": "172.20.0.2",
                     "body_bytes": self.plan["expected_event"]["body_bytes"],
                     "body_sha256": self.plan["expected_event"]["body_sha256"]}
            return result(json.dumps(event, separators=(",", ":")) + "\n")
        return result(code=1, error="unexpected command")


@pytest.fixture
def make_driver(tmp_path):
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"fake Docker CLI")
    plan = build_fake_gateway_probe_plan("a" * 32)
    def create(**kwargs):
        cli = FakeCLI(plan, **kwargs)
        driver = FakeRunningDockerDriver(
            run_id=plan["run_id"], docker_executable=str(executable),
            docker_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            run_command=cli)
        return plan, driver, cli
    return create


def _created(plan, driver):
    network = driver.create_network(plan["network_create"])
    gateway = driver.create_container(plan["gateway_create"])
    client = driver.create_container(plan["client_create"])
    return network, gateway, client


def test_exact_running_cleanup_and_strict_pending_line(make_driver):
    plan, driver, cli = make_driver()
    ids = _created(plan, driver)
    driver.start_container(GATEWAY_ID)
    driver.start_container(CLIENT_ID)
    assert b"FAKE_REQUEST_PENDING" in driver.pending_line(GATEWAY_ID, 10)
    assert driver.cleanup_running_owned(plan, *ids) == {
        "remaining_container_ids": [], "remaining_network_ids": []}
    assert cli.containers == {} and cli.network is None
    assert cli.calls.index(["container", "rm", "--force", CLIENT_ID]) \
        < cli.calls.index(["network", "rm", NETWORK_ID])


def test_lost_start_response_still_reconciles_running_owned_id(make_driver):
    plan, driver, cli = make_driver(lose_start=True)
    ids = _created(plan, driver)
    with pytest.raises(FakeCreatedDockerDenied, match="command failed"):
        driver.start_container(GATEWAY_ID)
    assert cli.containers["gateway"]["State"]["Running"] is True
    assert driver.cleanup_running_owned(plan, *ids) == {
        "remaining_container_ids": [], "remaining_network_ids": []}


def test_lost_create_response_reconciles_unstarted_container(make_driver):
    plan, driver, cli = make_driver(lose_client_create=True)
    network = driver.create_network(plan["network_create"])
    gateway = driver.create_container(plan["gateway_create"])
    with pytest.raises(FakeCreatedDockerDenied, match="command failed"):
        driver.create_container(plan["client_create"])
    assert driver.cleanup_running_owned(plan, network, gateway, None) == {
        "remaining_container_ids": [], "remaining_network_ids": []}
    assert cli.containers == {} and cli.network is None


@pytest.mark.parametrize("raw", ["not json\n", "{}\n", "{}\n{}\n"])
def test_invalid_or_multiple_log_lines_are_denied(make_driver, raw):
    plan, driver, _ = make_driver(log_override=raw)
    ids = _created(plan, driver)
    driver.start_container(GATEWAY_ID)
    with pytest.raises(ValueError):
        driver.pending_line(GATEWAY_ID, 10)
    assert driver.cleanup_running_owned(plan, *ids) == {
        "remaining_container_ids": [], "remaining_network_ids": []}


def test_stderr_on_log_read_is_denied(make_driver):
    plan, driver, _ = make_driver(log_override="", log_stderr="unexpected")
    ids = _created(plan, driver)
    driver.start_container(GATEWAY_ID)
    with pytest.raises(FakeCreatedDockerDenied, match="stderr denied"):
        driver.pending_line(GATEWAY_ID, 10)
    assert driver.cleanup_running_owned(plan, *ids) == {
        "remaining_container_ids": [], "remaining_network_ids": []}


def test_foreign_label_prevents_start_and_cleanup(make_driver):
    plan, driver, cli = make_driver(wrong_label=True)
    ids = _created(plan, driver)
    with pytest.raises(FakeCreatedDockerDenied, match="start identity denied"):
        driver.start_container(GATEWAY_ID)
    with pytest.raises(FakeCreatedDockerDenied, match="cleanup incomplete"):
        driver.cleanup_running_owned(plan, *ids)
    assert ["container", "rm", "--force", GATEWAY_ID] not in cli.calls


def test_unowned_start_and_wrong_pending_scope_have_no_cli_call(make_driver):
    plan, driver, cli = make_driver()
    _created(plan, driver)
    count = len(cli.calls)
    with pytest.raises(FakeCreatedDockerDenied, match="unowned start denied"):
        driver.start_container("f" * 64)
    with pytest.raises(FakeCreatedDockerDenied, match="pending reader scope denied"):
        driver.pending_line(CLIENT_ID, 10)
    assert len(cli.calls) == count
