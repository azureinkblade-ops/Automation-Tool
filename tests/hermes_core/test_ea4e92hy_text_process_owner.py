"""An injected fake controller exercises ownership; no receiver starts."""

import json
from dataclasses import replace

import pytest

from tests.hermes_core.durable_auth_test_support import qualification_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hj_agent_delegated_claim_owner import owner
from tests.hermes_core.test_ea4e92hu_text_ping_command import (
    PING_LEASE, PING_TASK, opencode_binding,
)
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_ping_command import build_agent_text_ping_command
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.agent_text_process_observation import (
    SQLiteAgentTextProcessObservationStore,
)
from tools.hermes_core.agent_text_process_owner import (
    AgentTextProcessOwner, TextProcessFinished, TextProcessStarted,
)
from tools.hermes_core.agent_text_report_candidate import preview_reported_text_ping_candidate


class FakeProcessController:
    def __init__(self, stdout_bytes):
        self.stdout_bytes = stdout_bytes
        self.starts = 0
        self.waits = 0
        self.kills = 0
        self.fail_start = False
        self.fail_wait = False
        self.expected_plan = None

    def prepare(self, witness, bridge):
        assert witness.lease.attempt_id == bridge.attempt_id
        return self.expected_plan

    def start(self, argv):
        assert tuple(argv)
        self.starts += 1
        if self.fail_start:
            raise RuntimeError("injected uncertain start")
        return TextProcessStarted("fake-owner-1", 1234)

    def wait(self, started):
        assert started.pid == 1234
        self.waits += 1
        if self.fail_wait:
            raise RuntimeError("injected wait fault")
        return TextProcessFinished(0, self.stdout_bytes, b"")

    def kill(self, started):
        assert started.pid == 1234
        self.kills += 1


def setup(tmp_path, agent):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True, task_changes=PING_TASK,
        lease_changes=PING_LEASE,
    )
    resolution = fake_resolution(agent)
    bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
    bridge = bridges.reserve(lease.attempt_id, resolution)
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    kwargs = {}
    if agent == "opencode-cli-agent":
        config, binding = opencode_binding(tmp_path)
        kwargs = {"opencode_config": config, "opencode_binding": binding}
    plan = build_agent_text_ping_command(witness, bridge, **kwargs)
    auth_store = qualification_store(tmp_path)
    claims = owner(authority, start, auth_store)
    intents = SQLiteAgentTextProcessIntentStore(claims.bridge_store, clock=lambda: NOW)
    intents.reserve(lease.attempt_id, plan.argv)
    observations = SQLiteAgentTextProcessObservationStore(
        intents, claims.fence_store, clock=lambda: NOW,
    )
    structured = terminal_outcome(witness).verified_result.payload["text"]
    stdout = (json.dumps({"type": "text", "text": structured}) + "\n").encode()
    controller = FakeProcessController(stdout)
    controller.expected_plan = plan
    authorization = claims.issue(lease.attempt_id, resolution).authorization
    return (authority, start, task, lease, plan, resolution, authorization,
            claims, observations, controller)


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_one_fake_process_report_then_reconcile_only(tmp_path, agent):
    (authority, start, task, lease, plan, resolution, authorization,
     claims, observations, controller) = setup(tmp_path, agent)
    try:
        disabled = AgentTextProcessOwner(claims, observations)
        assert disabled.execute_once(plan, resolution, authorization).reason == "NO_PROCESS_CONTROLLER"
        assert claims.fence_store.get(lease.attempt_id) is None
        current = AgentTextProcessOwner(claims, observations, controller=controller)
        state = current.execute_once(plan, resolution, authorization)
        assert state.status == "REPORTED_TERMINAL"
        assert state.terminal_hash == observations.get_terminal(lease.attempt_id).terminal_hash
        assert (controller.starts, controller.waits, controller.kills) == (1, 1, 0)
        assert preview_reported_text_ping_candidate(observations, lease.attempt_id)
        assert capture_store(authority, start).get(lease.attempt_id) is None
        assert authority.list_mailbox(task.originator_agent_id) == []
        assert current.execute_once(plan, resolution, authorization).status == "RECONCILE_ONLY"
        assert controller.starts == 1
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:04Z",
        )
        assert current.execute_once(plan, resolution, authorization).status == "RECONCILE_ONLY"
        assert controller.starts == 1
    finally:
        start.close()


def test_uncertain_start_is_never_retried(tmp_path):
    (authority, start, task, lease, plan, resolution, authorization,
     claims, observations, controller) = setup(tmp_path, "kilo-cli-agent")
    try:
        controller.fail_start = True
        current = AgentTextProcessOwner(claims, observations, controller=controller)
        assert current.execute_once(plan, resolution, authorization).reason == "PROCESS_START_UNCERTAIN"
        assert claims.fence_store.get(lease.attempt_id) is not None
        assert observations.get_start(lease.attempt_id) is None
        assert current.execute_once(plan, resolution, authorization).status == "UNKNOWN"
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:04Z",
        )
        assert current.execute_once(plan, resolution, authorization).status == "UNKNOWN"
        assert controller.starts == 1
    finally:
        start.close()


def test_wait_failure_requests_kill_and_never_restarts(tmp_path):
    (authority, start, _, lease, plan, resolution, authorization,
     claims, observations, controller) = setup(tmp_path, "opencode-cli-agent")
    try:
        controller.fail_wait = True
        current = AgentTextProcessOwner(claims, observations, controller=controller)
        state = current.execute_once(plan, resolution, authorization)
        assert state.status == "UNKNOWN"
        assert state.reason == "TERMINAL_WAIT_FAILED_KILL_REQUESTED"
        assert observations.get_start(lease.attempt_id) is not None
        assert observations.get_terminal(lease.attempt_id) is None
        assert controller.kills == 1
        assert current.execute_once(plan, resolution, authorization).status == "RECONCILE_ONLY"
        assert controller.starts == 1
    finally:
        start.close()


def test_start_report_failure_requests_kill_and_never_restarts(tmp_path):
    (authority, start, _, lease, plan, resolution, authorization,
     claims, observations, controller) = setup(tmp_path, "kilo-cli-agent")
    try:
        current = AgentTextProcessOwner(claims, observations, controller=controller)

        def fail_report(*args, **kwargs):
            raise RuntimeError("injected report failure")

        observations.record_start = fail_report
        state = current.execute_once(plan, resolution, authorization)
        assert state.status == "UNKNOWN"
        assert state.reason == "START_REPORT_FAILED_KILL_REQUESTED"
        assert controller.kills == 1
        assert observations.get_start(lease.attempt_id) is None
        assert current.execute_once(plan, resolution, authorization).status == "UNKNOWN"
        assert controller.starts == 1
    finally:
        start.close()


def test_divergent_plan_denies_before_claim_or_start(tmp_path):
    (authority, start, _, lease, plan, resolution, authorization,
     claims, observations, controller) = setup(tmp_path, "kilo-cli-agent")
    try:
        current = AgentTextProcessOwner(claims, observations, controller=controller)
        state = current.execute_once(
            replace(plan, bridge_hash="0" * 64), resolution, authorization,
        )
        assert state.status == "DENIED"
        assert claims.fence_store.get(lease.attempt_id) is None
        assert controller.starts == 0
    finally:
        start.close()


def test_controller_plan_mismatch_denies_before_claim(tmp_path):
    (authority, start, _, lease, plan, resolution, authorization,
     claims, observations, controller) = setup(tmp_path, "opencode-cli-agent")
    try:
        controller.expected_plan = replace(plan, argv_hash="0" * 64)
        current = AgentTextProcessOwner(claims, observations, controller=controller)
        assert current.execute_once(plan, resolution, authorization).reason == "PROCESS_PLAN_NOT_QUALIFIED"
        assert claims.fence_store.get(lease.attempt_id) is None
        assert controller.starts == 0
    finally:
        start.close()
