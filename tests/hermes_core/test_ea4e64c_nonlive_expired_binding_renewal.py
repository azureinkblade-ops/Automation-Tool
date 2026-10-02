"""EA-4E.64C explicit expired executor-binding renewal, non-live only."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.hermes_core.production_deployment_composition import (
    ProductionDeploymentCompositionError,
    ProductionDeploymentCompositionOwner,
    ProductionDeploymentPaths,
)


GOVERNING_COMMIT = "ae79785530421420b9e94c5605e520fbce5eaedb"


class FixedClock:
    def __init__(self, now: str) -> None:
        self.now = datetime.fromisoformat(now)

    def now_iso(self) -> str:
        return self.now.isoformat()

    def now_plus_seconds(self, seconds: int) -> str:
        return (self.now + timedelta(seconds=seconds)).isoformat()


class FakeKiloExecutor:
    executor_id = "RealKiloProductionExecutor"

    def __init__(self, counter: dict[str, int]) -> None:
        self.counter = counter

    def execute(self, _request):
        self.counter["calls"] += 1
        raise AssertionError("EA-4E.64C must not execute")


class ReadyPreflight:
    def config_for(self, receiver_id, **values):
        return {"receiver_id": receiver_id, **values}

    def check(self, _config):
        return SimpleNamespace(ready=True, failure_code=None)


def paths(tmp_path: Path) -> ProductionDeploymentPaths:
    return ProductionDeploymentPaths(
        invocation_store_path=tmp_path / "invocation.sqlite3",
        invocation_anchor_path=tmp_path / "invocation.anchor.json",
        activation_store_path=tmp_path / "activation.sqlite3",
        activation_anchor_path=tmp_path / "activation.anchor.json",
        binding_state_path=tmp_path / "binding.sqlite3",
    )


def provision(tmp_path, clock, counter, *, renew=False):
    return ProductionDeploymentCompositionOwner.provision(
        paths=paths(tmp_path),
        governing_commit=GOVERNING_COMMIT,
        provision_explicit=True,
        expired_binding_renewal_explicit=renew,
        clock=clock,
        credential_preflight=ReadyPreflight(),
        executor_factory=lambda: FakeKiloExecutor(counter),
    )


def test_expired_binding_requires_explicit_renewal(tmp_path):
    counter = {"calls": 0}
    provision(tmp_path, FixedClock("2026-09-11T10:00:00+00:00"), counter)
    with pytest.raises(ProductionDeploymentCompositionError) as exc:
        provision(tmp_path, FixedClock("2026-09-11T12:00:01+00:00"), counter)
    assert exc.value.reason == "PERSISTED_KILO_BINDING_EXPIRED"
    assert counter["calls"] == 0


def test_explicit_renewal_rotates_only_runtime_binding_identity(tmp_path):
    counter = {"calls": 0}
    first = provision(tmp_path, FixedClock("2026-09-11T10:00:00+00:00"), counter)
    first_payload = first.binding_store.load()
    first_lineage = first.activation_store.lineage()

    renewed = provision(
        tmp_path,
        FixedClock("2026-09-11T12:00:01+00:00"),
        counter,
        renew=True,
    )
    renewed_payload = renewed.binding_store.load()

    assert renewed.binding_handle.binding_id != first.binding_handle.binding_id
    assert renewed_payload["enablement"]["enablement_id"] != first_payload["enablement"]["enablement_id"]
    assert renewed_payload["enablement"]["expires_at"] == "2026-09-11T13:00:01+00:00"
    for key in ("executable_binding_id", "binary_path", "binary_sha256", "binary_version"):
        assert renewed_payload[key] == first_payload[key]
    for key in ("receiver_id", "transport_contract_id", "model_binding_id", "executor_identity", "executor_factory"):
        assert renewed_payload["enablement"][key] == first_payload["enablement"][key]
    assert renewed.activation_store.lineage() == first_lineage
    assert renewed.activation_store.has_outstanding() is False
    assert counter["calls"] == 0


def test_unexpired_binding_cannot_be_rotated_as_renewal(tmp_path):
    counter = {"calls": 0}
    first = provision(tmp_path, FixedClock("2026-09-11T10:00:00+00:00"), counter)
    with pytest.raises(ProductionDeploymentCompositionError) as exc:
        provision(
            tmp_path,
            FixedClock("2026-09-11T10:30:00+00:00"),
            counter,
            renew=True,
        )
    assert exc.value.reason == "PERSISTED_KILO_BINDING_NOT_EXPIRED"
    assert first.binding_store.load()["binding_id"] == first.binding_handle.binding_id
    assert counter["calls"] == 0


def test_renewed_binding_survives_reconstruction_without_refresh(tmp_path):
    counter = {"calls": 0}
    provision(tmp_path, FixedClock("2026-09-11T10:00:00+00:00"), counter)
    renewed = provision(
        tmp_path,
        FixedClock("2026-09-11T12:00:01+00:00"),
        counter,
        renew=True,
    )
    reopened = provision(
        tmp_path,
        FixedClock("2026-09-11T12:30:00+00:00"),
        counter,
    )
    assert reopened.binding_handle.binding_id == renewed.binding_handle.binding_id
    assert reopened.binding_handle.expires_at == renewed.binding_handle.expires_at
    assert counter["calls"] == 0
