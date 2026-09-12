"""EA-4E.47 strict non-live durable-store bootstrap qualification."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    AUTH_STORE_SCHEMA_ID,
    AUTH_STORE_SCHEMA_VERSION,
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_executor_binding import (
    ProductionExecutorBindingController,
)
from tools.hermes_core.production_invocation_auth_store_bootstrap import (
    ProductionInvocationAuthStoreBootstrapRequest,
    ProductionInvocationAuthStoreBootstrapper,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ProductionIssuancePolicy


TRIPWIRE_HITS = {
    "execution_authority": 0,
    "invocation_authority": 0,
    "claim": 0,
    "binding": 0,
    "registration": 0,
}


@pytest.fixture(autouse=True)
def nonlive_tripwires(monkeypatch):
    for key in TRIPWIRE_HITS:
        TRIPWIRE_HITS[key] = 0

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E47_{category.upper()}_TRIPWIRE")

        return reject

    monkeypatch.setattr(ProductionIssuancePolicy, "evaluate", trip("execution_authority"))
    monkeypatch.setattr(
        ProductionInvocationAuthorizationIssuer, "issue", trip("invocation_authority")
    )
    monkeypatch.setattr(DurableInvocationAuthorizationStore, "claim", trip("claim"))
    monkeypatch.setattr(ProductionExecutorBindingController, "bind", trip("binding"))
    monkeypatch.setattr(
        "tools.hermes_core.production_wiring.register_qualified_real_executors",
        trip("registration"),
    )
    yield
    assert all(value == 0 for value in TRIPWIRE_HITS.values())


def request(tmp_path: Path, **changes):
    fields = {
        "store_path": tmp_path / "invocation-authorization.sqlite3",
        "anchor_path": tmp_path / "invocation-authorization.anchor.json",
        "bootstrap_explicit": True,
    }
    fields.update(changes)
    return ProductionInvocationAuthStoreBootstrapRequest(**fields)


def bootstrapper():
    return ProductionInvocationAuthStoreBootstrapper()


def fake_payload():
    return {
        "invocation_authorization_id": "fake-ea4e47-auth",
        "receiver_id": "kilo-cli-agent",
        "binding_id": "fake-binding",
        "enablement_id": "fake-enablement",
        "execution_request_id": "fake-execution-request",
        "attempt_number": 1,
        "issued_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2026-01-01T00:01:00+00:00",
        "runtime_scope": "production",
        "delegation_class": "governed",
        "nonce": "fake-nonce",
    }


def reopen(result):
    return DurableInvocationAuthorizationStore(
        result.canonical_store_path,
        anchor_path=result.canonical_anchor_path,
    )


def test_missing_request():
    result = bootstrapper().bootstrap(None)
    assert result.bootstrap_decision == "DENY"
    assert result.bootstrap_reason == "MISSING_REQUEST"


def test_malformed_request():
    assert bootstrapper().bootstrap(object()).bootstrap_reason == "MALFORMED_REQUEST"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_store_path(tmp_path, value):
    result = bootstrapper().bootstrap(request(tmp_path, store_path=value))
    assert result.bootstrap_reason == "MISSING_STORE_PATH"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_anchor_path(tmp_path, value):
    result = bootstrapper().bootstrap(request(tmp_path, anchor_path=value))
    assert result.bootstrap_reason == "MISSING_ANCHOR_PATH"


@pytest.mark.parametrize("value", [None, False, 0, "true"])
def test_explicit_bootstrap_intent_required(tmp_path, value):
    result = bootstrapper().bootstrap(request(tmp_path, bootstrap_explicit=value))
    assert result.bootstrap_reason == "EXPLICIT_BOOTSTRAP_INTENT_REQUIRED"
    assert not (tmp_path / "invocation-authorization.sqlite3").exists()


@pytest.mark.parametrize(
    "value",
    [
        "automation_state.db",
        "AUTOMATION_STATE.DB",
        Path("nested") / ".." / "automation_state.db",
    ],
)
def test_automation_state_db_is_forbidden(tmp_path, monkeypatch, value):
    monkeypatch.chdir(tmp_path)
    result = bootstrapper().bootstrap(request(tmp_path, store_path=value))
    assert result.bootstrap_reason == "AUTOMATION_STATE_DB_FORBIDDEN"
    assert not (tmp_path / "automation_state.db").exists()


def test_home_relative_path_is_rejected(tmp_path):
    result = bootstrapper().bootstrap(request(tmp_path, store_path="~/auth.sqlite3"))
    assert result.bootstrap_reason == "INVALID_PATH"


def test_store_and_anchor_must_differ(tmp_path):
    same = tmp_path / "same.sqlite3"
    result = bootstrapper().bootstrap(
        request(tmp_path, store_path=same, anchor_path=same)
    )
    assert result.bootstrap_reason == "STORE_AND_ANCHOR_PATHS_MUST_DIFFER"


def test_absent_store_is_initialized_and_schema_validated(tmp_path):
    source = request(tmp_path)
    result = bootstrapper().bootstrap(source)
    assert result.bootstrap_decision == "INITIALIZED"
    assert result.bootstrap_reason == "STORE_CREATED_AND_SCHEMA_VALIDATED"
    assert result.requested_store_path == str(source.store_path)
    assert result.requested_anchor_path == str(source.anchor_path)
    assert result.canonical_store_path == str(Path(source.store_path).resolve())
    assert result.canonical_anchor_path == str(Path(source.anchor_path).resolve())
    assert result.schema_id == AUTH_STORE_SCHEMA_ID
    assert result.schema_version == AUTH_STORE_SCHEMA_VERSION
    assert result.store_instance_id
    assert result.store_generation == 1
    assert reopen(result).count() == 0


def test_existing_valid_store_is_not_reinitialized_or_replaced(tmp_path, monkeypatch):
    first = bootstrapper().bootstrap(request(tmp_path))
    database = Path(first.canonical_store_path)
    anchor = Path(first.canonical_anchor_path)
    before = (database.read_bytes(), anchor.read_bytes())

    def forbidden_initialize(*args, **kwargs):
        raise AssertionError("EXISTING_STORE_WAS_REINITIALIZED")

    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", forbidden_initialize)
    second = bootstrapper().bootstrap(request(tmp_path))
    assert second.bootstrap_decision == "ALREADY_INITIALIZED"
    assert second.store_instance_id == first.store_instance_id
    assert (database.read_bytes(), anchor.read_bytes()) == before


def test_repeat_bootstrap_preserves_existing_fake_data(tmp_path):
    first = bootstrapper().bootstrap(request(tmp_path))
    store = reopen(first)
    payload = fake_payload()
    store.persist_issued(
        issue_request_id="fake-ea4e47-issue",
        issue_request_hash=sha256_payload({"fake": "request"}),
        authorization_payload=payload,
    )
    generation = store.store_generation

    second = bootstrapper().bootstrap(request(tmp_path))
    reopened = reopen(second)
    assert second.bootstrap_decision == "ALREADY_INITIALIZED"
    assert reopened.count() == 1
    assert reopened.inspect_by_id(payload["invocation_authorization_id"]).authorization_payload == payload
    assert reopened.store_generation == generation


def test_existing_foreign_file_fails_closed_without_mutation(tmp_path):
    database = tmp_path / "invocation-authorization.sqlite3"
    anchor = tmp_path / "invocation-authorization.anchor.json"
    database.write_bytes(b"foreign database bytes")
    anchor.write_bytes(b"foreign anchor bytes")
    before = (database.read_bytes(), anchor.read_bytes())
    result = bootstrapper().bootstrap(request(tmp_path))
    assert result.bootstrap_reason == "EXISTING_INVALID_STORE"
    assert (database.read_bytes(), anchor.read_bytes()) == before


def test_incompatible_schema_fails_closed_without_migration(tmp_path):
    first = bootstrapper().bootstrap(request(tmp_path))
    database = Path(first.canonical_store_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE auth_store_metadata SET schema_version = 'unsupported' WHERE singleton = 1"
        )
        connection.commit()
    before = database.read_bytes()
    result = bootstrapper().bootstrap(request(tmp_path))
    assert result.bootstrap_reason == "EXISTING_INVALID_STORE"
    assert database.read_bytes() == before


@pytest.mark.parametrize("target", ["store", "anchor"])
def test_existing_directory_collision_fails_closed(tmp_path, target):
    store = tmp_path / "store.sqlite3"
    anchor = tmp_path / "anchor.json"
    selected = store if target == "store" else anchor
    selected.mkdir()
    result = bootstrapper().bootstrap(
        request(tmp_path, store_path=store, anchor_path=anchor)
    )
    expected = "EXISTING_DIRECTORY_TARGET" if target == "store" else "EXISTING_DIRECTORY_ANCHOR"
    assert result.bootstrap_reason == expected


@pytest.mark.parametrize("missing", ["store", "anchor"])
def test_parent_directory_must_already_exist(tmp_path, missing):
    store = tmp_path / ("missing" if missing == "store" else "present") / "store.sqlite3"
    anchor = tmp_path / ("missing" if missing == "anchor" else "present") / "anchor.json"
    (tmp_path / "present").mkdir()
    result = bootstrapper().bootstrap(
        request(tmp_path, store_path=store, anchor_path=anchor)
    )
    expected = "STORE_PARENT_DIRECTORY_REQUIRED" if missing == "store" else "ANCHOR_PARENT_DIRECTORY_REQUIRED"
    assert result.bootstrap_reason == expected
    assert not (tmp_path / "missing").exists()


def test_existing_store_without_anchor_fails_closed(tmp_path):
    database = tmp_path / "invocation-authorization.sqlite3"
    database.write_bytes(b"do not overwrite")
    result = bootstrapper().bootstrap(request(tmp_path))
    assert result.bootstrap_reason == "EXISTING_STORE_MISSING_ANCHOR"
    assert database.read_bytes() == b"do not overwrite"


def test_orphan_anchor_fails_closed(tmp_path):
    anchor = tmp_path / "invocation-authorization.anchor.json"
    anchor.write_bytes(b"do not overwrite")
    result = bootstrapper().bootstrap(request(tmp_path))
    assert result.bootstrap_reason == "ORPHAN_ANCHOR_WITHOUT_STORE"
    assert anchor.read_bytes() == b"do not overwrite"


def test_initializer_exception_fails_closed(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("isolated failure")

    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", explode)
    result = bootstrapper().bootstrap(request(tmp_path))
    assert result.bootstrap_decision == "DENY"
    assert result.bootstrap_reason == "INITIALIZER_EXCEPTION:RuntimeError"
    assert result.error_detail == "isolated failure"


def test_initializer_permission_error_fails_closed(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("isolated permission denial")

    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", denied)
    result = bootstrapper().bootstrap(request(tmp_path))
    assert result.bootstrap_decision == "DENY"
    assert result.bootstrap_reason == "INITIALIZER_EXCEPTION:PermissionError"
    assert result.error_detail == "isolated permission denial"


def test_schema_validation_failure_fails_closed(tmp_path, monkeypatch):
    class InvalidStore:
        @property
        def store_instance_id(self):
            raise RuntimeError("schema invalid")

    monkeypatch.setattr(
        DurableInvocationAuthorizationStore,
        "initialize",
        lambda *args, **kwargs: InvalidStore(),
    )
    result = bootstrapper().bootstrap(request(tmp_path))
    assert result.bootstrap_decision == "DENY"
    assert result.bootstrap_reason == "SCHEMA_VALIDATION_FAILURE"


def test_equivalent_absent_inputs_produce_equivalent_decisions(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    one = bootstrapper().bootstrap(request(left))
    two = bootstrapper().bootstrap(request(right))
    assert (one.bootstrap_decision, one.bootstrap_reason, one.schema_id, one.schema_version) == (
        two.bootstrap_decision,
        two.bootstrap_reason,
        two.schema_id,
        two.schema_version,
    )


def test_imports_do_not_initialize_store(monkeypatch):
    calls = 0
    original = DurableInvocationAuthorizationStore.initialize

    def spy(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", spy)
    __import__("tools.hermes_core.production_invocation_auth_store_bootstrap")
    __import__("tools.hermes_core.production_app_factory")
    __import__("tools.hermes_core.production_entrypoint")
    __import__("tools.hermes_core.production_app_invocation_authorization")
    assert calls == 0


def test_factory_missing_store_remains_reopen_only(tmp_path, monkeypatch):
    from tools.hermes_core.production_app_factory import (
        ProductionAppFactory,
        ProductionAppFactoryConfig,
        ProductionAppFactoryError,
    )
    from tools.hermes_core.production_issuance import ClockCollaborator
    from tools.hermes_core.production_wiring import ProductionWiringConfig

    calls = 0

    def forbidden_initialize(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("FACTORY_BOOTSTRAPPED_STORE")

    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", forbidden_initialize)
    config = ProductionAppFactoryConfig(
        wiring=ProductionWiringConfig(
            auth_store_path=tmp_path / "missing.sqlite3",
            auth_anchor_path=tmp_path / "missing.anchor.json",
        ),
        clock=ClockCollaborator(now="2026-01-01T00:00:00+00:00"),
        register_real_executors=False,
    )
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(config)
    assert exc.value.reason == "MISSING_ESTABLISHED_AUTH_STORE"
    assert calls == 0


def test_module_has_no_default_or_destructive_runtime_capability():
    source = Path(
        "tools/hermes_core/production_invocation_auth_store_bootstrap.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "os.environ",
        "subprocess",
        ".unlink(",
        ".rename(",
        ".replace(",
        ".issue(",
        ".claim(",
        ".consume(",
        ".bind(",
        ".execute(",
    )
    assert all(token not in source for token in forbidden)
