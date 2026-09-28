"""Fake creator-owner state tests; no native path or process is used."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import inspect

import pytest

from tools import ea4e92av_fake_creator_owner as subject
from tools.ea4e92s_creator_preflight import prepare_creation_call_plan
from tools.ea4e92s_suspended_process import SuspendedCreationResult
from tests.hermes_core.test_ea4e92as_creator_preflight import identity_fixture
from tests.hermes_core.test_ea4e92aq_native_buffers import prepared
from tests.hermes_core.test_ea4e92s_probe_admission import policy


def setup():
    reviewed = policy()
    buffers, attributes = prepared(reviewed)
    pins, inspector = identity_fixture(reviewed)
    plan = prepare_creation_call_plan(reviewed, buffers, pins, inspector)
    return subject.FakeCreatorOwner(plan), plan, inspector, attributes


def fake_result(**changes):
    return replace(SuspendedCreationResult(
        101, 102, 201, 202, True, True, True), **changes)


def test_one_attempt_return_and_cleanup_remain_fake_only():
    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        assert owner.attempts == 1
        assert owner.state == "call_in_progress"
        result = fake_result()
        owner.record_fake_return(plan, result)
        assert owner.state == "returned_untrusted"
        assert not hasattr(owner, "verified")
        assert not hasattr(owner, "resume_authorized")
        owner.begin_fake_cleanup(plan, result)
        owner.record_fake_cleanup(plan, result, confirmed=True)
        assert owner.state == "closed_fake"
    finally:
        attributes.close()


def test_fake_return_predicates_never_create_trusted_verdict():
    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        owner.record_fake_return(plan, fake_result(suspended=False))
        assert owner.state == "returned_untrusted"
    finally:
        attributes.close()


def test_buffer_owner_or_path_drift_after_begin_denied():
    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        path = plan.reviewed.bootstrap.path
        inspector.snapshots[path] = replace(
            inspector.snapshots[path], file_id=b"x" * 16)
        with pytest.raises(subject.FakeCreatorDenied):
            owner.record_fake_return(plan, fake_result())
        assert owner.state == "unknown"
    finally:
        attributes.close()

    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        attributes.close()
        with pytest.raises(subject.FakeCreatorDenied):
            owner.record_fake_return(plan, fake_result())
        assert owner.state == "unknown"
    finally:
        attributes.close()


@pytest.mark.parametrize("failure", ["foreign_plan", "stale_path", "closed_owner"])
def test_begin_denies_wrong_owner_or_preflight(failure):
    owner, plan, inspector, attributes = setup()
    try:
        if failure == "foreign_plan":
            candidate = replace(plan)
        else:
            candidate = plan
            if failure == "stale_path":
                path = plan.reviewed.runtime.path
                inspector.snapshots[path] = replace(
                    inspector.snapshots[path], file_id=b"x" * 16)
            else:
                attributes.close()
        with pytest.raises(subject.FakeCreatorDenied):
            owner.begin_fake_call(candidate, inspector)
        assert owner.state == "unknown"
        assert owner.attempts == 0
    finally:
        attributes.close()


@pytest.mark.parametrize("result", [
    object(), fake_result(process_handle=0),
    fake_result(thread_handle=101), fake_result(process_id=0),
])
def test_malformed_fake_return_is_sticky_unknown(result):
    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        with pytest.raises(subject.FakeCreatorDenied):
            owner.record_fake_return(plan, result)
        assert owner.state == "unknown"
        assert owner.attempts == 1
        assert owner.result is result
    finally:
        attributes.close()


def test_cancel_before_and_during_attempt():
    owner, plan, inspector, attributes = setup()
    try:
        owner.cancel()
        assert owner.state == "cancelled"
        with pytest.raises(subject.FakeCreatorDenied):
            owner.begin_fake_call(plan, inspector)
        assert owner.state == "unknown"
    finally:
        attributes.close()

    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        owner.cancel()
        assert owner.state == "unknown"
        with pytest.raises(subject.FakeCreatorDenied):
            owner.record_fake_return(plan, fake_result())
    finally:
        attributes.close()


def test_cleanup_replay_foreign_result_and_unconfirmed_denied():
    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        result = fake_result()
        owner.record_fake_return(plan, result)
        with pytest.raises(subject.FakeCreatorDenied):
            owner.begin_fake_cleanup(plan, replace(result))
        assert owner.state == "unknown"
    finally:
        attributes.close()

    owner, plan, inspector, attributes = setup()
    try:
        owner.begin_fake_call(plan, inspector)
        result = fake_result()
        owner.record_fake_return(plan, result)
        owner.begin_fake_cleanup(plan, result)
        with pytest.raises(subject.FakeCreatorDenied):
            owner.record_fake_cleanup(plan, result, confirmed=False)
        assert owner.state == "unknown"
    finally:
        attributes.close()


def test_concurrent_fake_call_has_one_attempt_only():
    owner, plan, inspector, attributes = setup()
    try:
        def attempt(_):
            try:
                owner.begin_fake_call(plan, inspector)
                return True
            except subject.FakeCreatorDenied:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        assert results.count(True) == 1
        assert owner.attempts == 1
        assert owner.state == "unknown"
    finally:
        attributes.close()


def test_source_has_no_launch_or_native_capability():
    source = inspect.getsource(subject)
    for forbidden in ("WinDLL", "CreateProcessW", "ResumeThread", "subprocess",
                      "Popen", "socket", "requests", "OpenProcess"):
        assert forbidden not in source
