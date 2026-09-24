"""Fake-only lifecycle ordering; no real resume or external process."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import inspect

import pytest

from tools import ea4e92s_fake_lifecycle as subject
from tools.ea4e92s_provenance_observation import UntrustedCreationObservation
from tests.hermes_core.test_ea4e92af_provenance_observation import setup


def lifecycle():
    receipt, owned = setup()
    return subject.FakeSuspendedLifecycle(receipt), receipt, owned


def observed(model, receipt):
    model.observe(UntrustedCreationObservation(
        receipt, "reviewed-profile", b"fake-sid"))


def test_fake_happy_path_has_no_production_permit():
    model, receipt, owned = lifecycle()
    observed(model, receipt)
    assert model.consume_test_transition(owned, receipt) is None
    assert model.state == "consumed"
    assert not hasattr(model, "resume_authorized")


def test_early_transition_is_sticky_unknown():
    model, receipt, owned = lifecycle()
    with pytest.raises(subject.FakeLifecycleDenied):
        model.consume_test_transition(owned, receipt)
    assert model.state == "unknown"
    with pytest.raises(subject.FakeLifecycleDenied):
        observed(model, receipt)


def test_cross_receipt_and_owner_deny():
    model, receipt, owned = lifecycle()
    observed(model, receipt)
    with pytest.raises(subject.FakeLifecycleDenied):
        model.consume_test_transition(owned, replace(receipt, request_id="other"))
    assert model.state == "unknown"

    model, receipt, owned = lifecycle()
    observed(model, receipt)
    with pytest.raises(subject.FakeLifecycleDenied):
        model.consume_test_transition(object(), receipt)
    assert model.state == "unknown"


def test_foreign_observation_and_owner_drift_deny():
    model, receipt, owned = lifecycle()
    with pytest.raises(subject.FakeLifecycleDenied):
        observed(model, replace(receipt, request_id="other"))
    assert model.state == "unknown"

    model, receipt, owned = lifecycle()
    observed(model, receipt)
    owned.creation_owner.security.attributes.keepalive[0][0] = 99
    with pytest.raises(subject.FakeLifecycleDenied):
        model.consume_test_transition(owned, receipt)
    assert model.state == "unknown"

    model, receipt, owned = lifecycle()
    observed(model, receipt)
    owned.state = "unknown"
    with pytest.raises(subject.FakeLifecycleDenied):
        model.consume_test_transition(owned, receipt)
    assert model.state == "unknown"


def test_cancel_and_replay_deny():
    model, receipt, owned = lifecycle()
    observed(model, receipt)
    model.cancel()
    with pytest.raises(subject.FakeLifecycleDenied):
        model.consume_test_transition(owned, receipt)
    assert model.state == "unknown"

    model, receipt, owned = lifecycle()
    observed(model, receipt)
    model.consume_test_transition(owned, receipt)
    with pytest.raises(subject.FakeLifecycleDenied):
        model.consume_test_transition(owned, receipt)
    assert model.state == "unknown"


def test_concurrent_fake_consumption_has_one_success():
    model, receipt, owned = lifecycle()
    observed(model, receipt)

    def attempt(_):
        try:
            model.consume_test_transition(owned, receipt)
            return True
        except subject.FakeLifecycleDenied:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(True) == 1
    assert results.count(False) == 7


def test_source_has_no_native_or_launch_capability():
    source = inspect.getsource(subject)
    for forbidden in (
            "WinDLL", "CreateProcessW", "ResumeThread", "subprocess",
            "OpenProcess", "OpenThread", "socket", "requests"):
        assert forbidden not in source
