"""Default-disabled app wiring for read-only local-profile inspection."""

import inspect

import app

from tools.hermes_core import agent_local_docker_operator_token as token
from tools.hermes_core.local_container_app_host_admission import (
    LocalAppHostPolicy,
    LocalAppHostRequest,
)


APP_ID = "12fd62da-967f-4920-8670-a4a2ad380e23"
STORE_ID = "29e2b538-5534-4211-9caf-a657141a5584"
SID = "S-1-5-21-1234567890-123456789-123456789-1001"
COMMIT = "a" * 40


class Store:
    reads = 0

    def _connection(self):
        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

        return Connection()

    def _verify_store_identity(self, _connection):
        self.reads += 1
        return STORE_ID, 4


def test_app_inspection_is_explicit_and_default_disabled(monkeypatch):
    monkeypatch.setattr(app, "_LOCAL_CONTAINER_APP_HOST_CONTEXT", None)
    request = LocalAppHostRequest(APP_ID, STORE_ID, 4, COMMIT)
    assert app.inspect_local_container_app_host(request).reason == (
        "LOCAL_PROFILE_DISABLED"
    )
    assert "configure_local_container_app_host" not in inspect.getsource(app.main)


def test_app_inspection_reads_context_only_when_enabled(monkeypatch):
    monkeypatch.setattr(app, "_LOCAL_CONTAINER_APP_HOST_CONTEXT", None)
    monkeypatch.setattr(token, "read_current_windows_account_sid", lambda: SID)
    policy = LocalAppHostPolicy(APP_ID, SID, STORE_ID, 4, COMMIT, enabled=True)
    request = LocalAppHostRequest(APP_ID, STORE_ID, 4, COMMIT)
    store = Store()
    app.configure_local_container_app_host(policy, store)
    assert app.inspect_local_container_app_host(request).reason == (
        "LOCAL_PROFILE_DISABLED"
    )
    assert store.reads == 0
    app.configure_local_container_app_host(policy, store, enabled=True)
    assert app.inspect_local_container_app_host(request).reason == (
        "LOCAL_PROFILE_CONTEXT_ONLY"
    )
    assert store.reads == 1


def test_app_inspection_denies_stale_store(monkeypatch):
    monkeypatch.setattr(app, "_LOCAL_CONTAINER_APP_HOST_CONTEXT", None)
    monkeypatch.setattr(token, "read_current_windows_account_sid", lambda: SID)
    policy = LocalAppHostPolicy(APP_ID, SID, STORE_ID, 4, COMMIT, enabled=True)
    request = LocalAppHostRequest(APP_ID, STORE_ID, 3, COMMIT)
    store = Store()
    app.configure_local_container_app_host(policy, store, enabled=True)
    assert app.inspect_local_container_app_host(request).reason == (
        "LOCAL_PROFILE_REQUEST_MISMATCH"
    )
    assert store.reads == 0
