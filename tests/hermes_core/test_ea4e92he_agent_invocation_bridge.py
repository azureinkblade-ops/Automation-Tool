"""Fake-only cross-domain request identity qualification."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tools.hermes_core.agent_invocation_bridge import bind_agent_invocation_request
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.governed_bound_executor import GovernedExecutorResolution
from tools.hermes_core.production_execution import FakeKiloExecutor, FakeOpenCodeExecutor
from tools.hermes_core.production_executor_binding import (
    ExecutorRegistry, ProductionExecutorBindingHandle,
)

NOW = datetime(2026, 8, 27, 12, 5, 4, tzinfo=timezone.utc)


def fake_resolution(agent, *, binding_id="executor-binding-1", expiry="2026-08-27T12:09:00+00:00"):
    executor = FakeKiloExecutor() if agent == "kilo-cli-agent" else FakeOpenCodeExecutor()
    registry = ExecutorRegistry()
    registry.register(agent, executor)
    handle = ProductionExecutorBindingHandle(
        binding_id=binding_id,
        enablement_id="enablement-1",
        receiver_id=agent,
        executor_identity=executor.executor_id,
        bound_at="2026-08-27T12:04:00+00:00",
        expires_at=expiry,
        registry=registry,
    )
    return GovernedExecutorResolution.success(executor, handle)


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_bridge_binds_distinct_binding_domains_and_stable_request(tmp_path, agent):
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        resolution = fake_resolution(agent)
        bridge = bind_agent_invocation_request(witness, resolution, now=NOW)
        assert bridge.verify_hash()
        assert bridge == bind_agent_invocation_request(witness, resolution, now=NOW)
        assert bridge.execution_request_id.startswith("agent-exec-")
        assert bridge.attempt_id == lease.attempt_id
        assert bridge.receipt_hash == witness.receipt.artifact_hash
        assert bridge.start_result_hash == witness.start_result.artifact_hash
        assert bridge.runtime_binding_id == witness.launch.runtime_binding_id
        assert bridge.runtime_binding_hash == witness.launch.runtime_binding_hash
        assert bridge.executor_binding_id == resolution.binding_id
        assert bridge.runtime_binding_id != bridge.executor_binding_id
        assert not replace(bridge, executor_binding_id="swapped").verify_hash()
    finally:
        start.close()


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_swapped_or_stale_executor_binding_denied(tmp_path, agent):
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        resolution = fake_resolution(agent)
        for changed in (
            replace(resolution, receiver_id="wrong-agent"),
            replace(resolution, binding_id="wrong-binding"),
            replace(resolution, expires_at="2026-08-27T12:08:00+00:00"),
            fake_resolution(agent, expiry="2026-08-27T12:05:00+00:00"),
            GovernedExecutorResolution.reject("NO_BINDING"),
        ):
            with pytest.raises(DelegationIntegrityError):
                bind_agent_invocation_request(witness, changed, now=NOW)
        registry = ExecutorRegistry()
        registry.register(agent, FakeKiloExecutor())
        with pytest.raises(DelegationIntegrityError):
            bind_agent_invocation_request(
                witness, replace(resolution, binding_handle=replace(
                    resolution.binding_handle, registry=registry,
                )), now=NOW,
            )
    finally:
        start.close()


def test_codex_and_forged_start_witness_denied(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        with pytest.raises(DelegationIntegrityError):
            bind_agent_invocation_request(
                witness, fake_resolution("kilo-cli-agent"), now=NOW,
            )
    finally:
        start.close()
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path / "kilo", "kilo-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="witness mismatch"):
            bind_agent_invocation_request(
                replace(witness, bound=replace(witness.bound, start_result_hash="0" * 64)),
                fake_resolution("kilo-cli-agent"), now=NOW,
            )
    finally:
        start.close()


def test_bridge_denies_expired_binding_at_current_time(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="expired"):
            bind_agent_invocation_request(
                witness, fake_resolution("kilo-cli-agent", expiry="2026-08-27T12:05:03+00:00"),
                now=NOW,
            )
        with pytest.raises(DelegationIntegrityError, match="inputs denied"):
            bind_agent_invocation_request(
                witness, fake_resolution("kilo-cli-agent"),
                now=datetime(2026, 8, 27, 12, 5, 4),
            )
    finally:
        start.close()
