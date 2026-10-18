"""Fake-only app-instance ownership state, without launching app.py."""

from dataclasses import replace

import pytest

from tools.ea4e92lq_app_instance_owner import (
    AppInstanceDenied,
    AppInstanceOwner,
    AppInstanceUnknown,
    AppLaunchReceipt,
    AppProcessObservation,
)


LAUNCHER_ID = "92aa3d25-728d-49f0-9e55-e611b39ea9a8"
INSTANCE_ID = "4ff38c48-eb14-4dbb-953c-110ce8c0661b"
PACKAGE = "a" * 64
RECEIPT = AppLaunchReceipt(LAUNCHER_ID, INSTANCE_ID, PACKAGE, 101, 202)
LIVE = AppProcessObservation(101, 202, INSTANCE_ID, PACKAGE, True)


class FakeLauncher:
    def __init__(self, receipt=RECEIPT, observation=LIVE):
        self.receipt = receipt
        self.observation = observation
        self.launches = 0
        self.observations = []
        self.closes = []

    def launch(self, *, launcher_instance_id, package_sha256):
        assert (launcher_instance_id, package_sha256) == (LAUNCHER_ID, PACKAGE)
        self.launches += 1
        return self.receipt

    def observe(self, process_handle):
        self.observations.append(process_handle)
        return self.observation

    def close_process_handle(self, process_handle):
        self.closes.append(process_handle)
        return True


def owner(launcher):
    return AppInstanceOwner(
        launcher, launcher_instance_id=LAUNCHER_ID, package_sha256=PACKAGE)


def test_exact_launch_receipt_and_live_observation():
    launcher = FakeLauncher()
    subject = owner(launcher)
    assert subject.start() is None
    assert subject.resolve_live() is RECEIPT
    assert launcher.observations == [101]
    assert subject.state == "OWNED"
    with pytest.raises(AppInstanceDenied, match="cannot replay"):
        subject.start()
    assert launcher.launches == 1


@pytest.mark.parametrize("bad", [
    None,
    replace(RECEIPT, launcher_instance_id=INSTANCE_ID),
    replace(RECEIPT, app_instance_nonce=LAUNCHER_ID),
    replace(RECEIPT, package_sha256="b" * 64),
    replace(RECEIPT, process_handle=0),
    replace(RECEIPT, process_handle=True),
    replace(RECEIPT, process_id=0),
])
def test_malformed_or_conflicting_launch_is_unknown_and_never_retried(bad):
    launcher = FakeLauncher(receipt=bad)
    subject = owner(launcher)
    with pytest.raises(AppInstanceUnknown):
        subject.start()
    assert subject.state == "UNKNOWN"
    with pytest.raises(AppInstanceDenied):
        subject.start()
    assert launcher.launches == 1


def test_ambiguous_launch_exception_cannot_retry():
    launcher = FakeLauncher()
    def ambiguous(**kwargs):
        launcher.launches += 1
        raise OSError("unknown launch outcome")
    launcher.launch = ambiguous
    subject = owner(launcher)
    with pytest.raises(AppInstanceUnknown):
        subject.start()
    with pytest.raises(AppInstanceDenied):
        subject.start()
    assert launcher.launches == 1


@pytest.mark.parametrize("bad", [
    None,
    replace(LIVE, process_handle=303),
    replace(LIVE, process_id=303),
    replace(LIVE, app_instance_nonce=LAUNCHER_ID),
    replace(LIVE, package_sha256="b" * 64),
    replace(LIVE, alive=1),
])
def test_process_drift_never_returns_retained_handle(bad):
    launcher = FakeLauncher(observation=bad)
    subject = owner(launcher)
    subject.start()
    with pytest.raises(AppInstanceUnknown):
        subject.resolve_live()
    assert subject.state == "UNKNOWN"
    with pytest.raises(AppInstanceDenied):
        subject.resolve_live()


def test_exit_closes_only_exact_retained_handle_once():
    launcher = FakeLauncher(observation=replace(LIVE, alive=False))
    subject = owner(launcher)
    subject.start()
    with pytest.raises(AppInstanceDenied, match="exited"):
        subject.resolve_live()
    assert subject.state == "EXITED"
    subject.close_exited()
    assert subject.state == "CLOSED"
    assert launcher.closes == [101]
    with pytest.raises(AppInstanceDenied):
        subject.close_exited()


def test_unconfirmed_close_remains_unknown():
    launcher = FakeLauncher(observation=replace(LIVE, alive=False))
    launcher.close_process_handle = lambda handle: False
    subject = owner(launcher)
    subject.start()
    with pytest.raises(AppInstanceDenied):
        subject.resolve_live()
    with pytest.raises(AppInstanceUnknown):
        subject.close_exited()
    assert subject.state == "UNKNOWN"


def test_observation_exception_remains_unknown():
    launcher = FakeLauncher()
    def unavailable(handle):
        raise OSError("process observation failed")
    launcher.observe = unavailable
    subject = owner(launcher)
    subject.start()
    with pytest.raises(AppInstanceUnknown):
        subject.resolve_live()
    assert subject.state == "UNKNOWN"


def test_close_exception_remains_unknown():
    launcher = FakeLauncher(observation=replace(LIVE, alive=False))
    def unavailable(handle):
        raise OSError("close outcome failed")
    launcher.close_process_handle = unavailable
    subject = owner(launcher)
    subject.start()
    with pytest.raises(AppInstanceDenied):
        subject.resolve_live()
    with pytest.raises(AppInstanceUnknown):
        subject.close_exited()
    assert subject.state == "UNKNOWN"


@pytest.mark.parametrize("launcher_id,package", [
    ("bad", PACKAGE),
    (LAUNCHER_ID, "A" * 64),
    (LAUNCHER_ID, "bad"),
])
def test_invalid_expected_identity_rejected_before_launcher_call(
        launcher_id, package):
    launcher = FakeLauncher()
    with pytest.raises(AppInstanceDenied):
        AppInstanceOwner(
            launcher, launcher_instance_id=launcher_id,
            package_sha256=package)
    assert launcher.launches == 0
