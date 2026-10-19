"""Fake-observer checks for the accepted local app-host trust profile."""

from dataclasses import replace

import pytest

from tools.hermes_core.local_container_app_host_admission import (
    LocalAppHostPolicy,
    LocalAppHostRequest,
    check_local_app_host,
)


APP_ID = "12fd62da-967f-4920-8670-a4a2ad380e23"
STORE_ID = "29e2b538-5534-4211-9caf-a657141a5584"
SID = "S-1-5-21-1234567890-123456789-123456789-1001"
COMMIT = "a" * 40


@pytest.fixture
def context():
    policy = LocalAppHostPolicy(
        app_instance_id=APP_ID, account_sid=SID,
        store_instance_id=STORE_ID, store_generation=4,
        governing_commit=COMMIT, enabled=True,
    )
    request = LocalAppHostRequest(
        app_instance_id=APP_ID, store_instance_id=STORE_ID,
        store_generation=4, governing_commit=COMMIT,
    )
    return policy, request


def assess(context, *, account_reader=None, store_reader=None):
    policy, request = context
    return check_local_app_host(
        policy, request,
        account_reader=account_reader or (lambda: SID),
        store_reader=store_reader or (lambda: (STORE_ID, 4)),
    )


def test_matching_context_is_not_authority(context):
    assert assess(context).reason == "LOCAL_PROFILE_CONTEXT_ONLY"


def test_default_disabled(context):
    policy, request = context
    assert assess((replace(policy, enabled=False), request)).decision == "DENY"


@pytest.mark.parametrize("field,value", [
    ("profile_id", "strict-92at"),
    ("app_instance_id", "not-an-id"),
    ("account_sid", "untrusted"),
    ("store_instance_id", "not-an-id"),
    ("store_generation", 0),
    ("store_generation", True),
    ("governing_commit", "A" * 40),
])
def test_malformed_policy_denied(context, field, value):
    policy, request = context
    assert assess((replace(policy, **{field: value}), request)).reason == (
        "LOCAL_PROFILE_POLICY_INVALID"
    )


@pytest.mark.parametrize("field,value", [
    ("profile_id", "strict-92at"),
    ("app_instance_id", "a" * 40),
    ("store_instance_id", "b" * 40),
    ("store_generation", 5),
    ("store_generation", True),
    ("governing_commit", "b" * 40),
])
def test_foreign_or_stale_request_denied(context, field, value):
    policy, request = context
    assert assess((policy, replace(request, **{field: value}))).reason == (
        "LOCAL_PROFILE_REQUEST_MISMATCH"
    )


def test_observed_account_mismatch_denied(context):
    assert assess(context, account_reader=lambda: "S-1-5-18").reason == (
        "LOCAL_PROFILE_ACCOUNT_MISMATCH"
    )


def test_store_rollback_and_replacement_denied(context):
    for observation in ((STORE_ID, 3), ("b" * 36, 4)):
        assert assess(context, store_reader=lambda: observation).reason == (
            "LOCAL_PROFILE_STORE_MISMATCH"
        )


def test_observer_failure_denied(context):
    def fail():
        raise OSError("unavailable")

    assert assess(context, account_reader=fail).reason == (
        "LOCAL_PROFILE_OBSERVATION_UNAVAILABLE"
    )
