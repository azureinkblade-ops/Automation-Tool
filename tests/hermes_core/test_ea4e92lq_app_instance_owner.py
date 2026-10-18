"""Fake-only app-instance ownership state, without launching app.py."""

from dataclasses import replace

import pytest

from tools.ea4e92lq_app_instance_owner import (
    AppInstanceDenied,
    AppInstanceOwner,
    AppInstanceUnknown,
    AppLaunchReceipt,
    AppPackageObservation,
    AppProcessObservation,
)
from tools.ea4e92s_retained_snapshot_provider import ProcessQuery


LAUNCHER_ID = "92aa3d25-728d-49f0-9e55-e611b39ea9a8"
INSTANCE_ID = "4ff38c48-eb14-4dbb-953c-110ce8c0661b"
PACKAGE = "a" * 64
RECEIPT = AppLaunchReceipt(LAUNCHER_ID, INSTANCE_ID, PACKAGE, 101, 202, 303)
LIVE = AppProcessObservation(101, 202, INSTANCE_ID, PACKAGE, True, 303)


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
        launcher, launcher_instance_id=LAUNCHER_ID, package_sha256=PACKAGE,
        fake_only=True)


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
    replace(RECEIPT, process_creation_time_100ns=0),
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
    replace(LIVE, process_creation_time_100ns=304),
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


class FakeProcessApi:
    def __init__(self, query=ProcessQuery(202, 303, True)):
        self.query = query
        self.queries = []
        self.closes = []

    def query_process(self, handle):
        self.queries.append(handle)
        return self.query

    def close_process(self, handle):
        self.closes.append(handle)
        return True


class FakePackageApi:
    def __init__(self, observation=AppPackageObservation(PACKAGE, True)):
        self.observation = observation
        self.receipts = []

    def observe_package(self, receipt):
        self.receipts.append(receipt)
        return self.observation


def test_kernel_query_uses_retained_handle_not_launcher_observation():
    launcher = FakeLauncher(observation=None)
    api = FakeProcessApi()
    package_api = FakePackageApi()
    subject = AppInstanceOwner(
        launcher, launcher_instance_id=LAUNCHER_ID,
        package_sha256=PACKAGE, process_api=api,
        package_api=package_api)
    subject.start()
    assert subject.resolve_live() is RECEIPT
    assert api.queries == [101]
    assert package_api.receipts == [RECEIPT]
    assert launcher.observations == []


@pytest.mark.parametrize("query", [
    ProcessQuery(203, 303, True),
    ProcessQuery(202, 304, True),
    ProcessQuery(202, 303, 1),
    ProcessQuery(202, 303.0, True),
    ProcessQuery(True, 303, True),
    None,
])
def test_kernel_query_drift_or_malformed_result_fails_closed(query):
    api = FakeProcessApi(query)
    subject = AppInstanceOwner(
        FakeLauncher(), launcher_instance_id=LAUNCHER_ID,
        package_sha256=PACKAGE, process_api=api,
        package_api=FakePackageApi())
    subject.start()
    with pytest.raises(AppInstanceUnknown):
        subject.resolve_live()
    assert subject.state == "UNKNOWN"


def test_kernel_query_exit_closes_only_retained_handle():
    api = FakeProcessApi(ProcessQuery(202, 303, False))
    subject = AppInstanceOwner(
        FakeLauncher(), launcher_instance_id=LAUNCHER_ID,
        package_sha256=PACKAGE, process_api=api,
        package_api=FakePackageApi())
    subject.start()
    with pytest.raises(AppInstanceDenied, match="exited"):
        subject.resolve_live()
    subject.close_exited()
    assert api.closes == [101]
    assert subject.state == "CLOSED"


@pytest.mark.parametrize("observation", [
    None,
    AppPackageObservation("b" * 64, True),
    AppPackageObservation(PACKAGE, False),
    AppPackageObservation(PACKAGE, 1),
])
def test_native_package_drift_denies_before_process_query(observation):
    api = FakeProcessApi()
    package_api = FakePackageApi(observation)
    subject = AppInstanceOwner(
        FakeLauncher(), launcher_instance_id=LAUNCHER_ID,
        package_sha256=PACKAGE, process_api=api,
        package_api=package_api)
    subject.start()
    with pytest.raises(AppInstanceUnknown):
        subject.resolve_live()
    assert subject.state == "UNKNOWN"
    assert package_api.receipts == [RECEIPT]
    assert api.queries == []


def test_native_package_is_reobserved_on_each_resolution():
    package_api = FakePackageApi()
    subject = AppInstanceOwner(
        FakeLauncher(), launcher_instance_id=LAUNCHER_ID,
        package_sha256=PACKAGE, process_api=FakeProcessApi(),
        package_api=package_api)
    subject.start()
    assert subject.resolve_live() is RECEIPT
    package_api.observation = AppPackageObservation("b" * 64, True)
    with pytest.raises(AppInstanceUnknown):
        subject.resolve_live()
    assert len(package_api.receipts) == 2


@pytest.mark.parametrize("options", [
    {},
    {"process_api": FakeProcessApi()},
    {"package_api": FakePackageApi()},
    {"fake_only": True, "process_api": FakeProcessApi(),
     "package_api": FakePackageApi()},
])
def test_owner_requires_explicit_native_pair_or_fake_mode(options):
    with pytest.raises(AppInstanceDenied, match="dependencies missing"):
        AppInstanceOwner(
            FakeLauncher(), launcher_instance_id=LAUNCHER_ID,
            package_sha256=PACKAGE, **options)


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
            package_sha256=package, fake_only=True)
    assert launcher.launches == 0
