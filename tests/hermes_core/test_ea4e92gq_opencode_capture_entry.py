"""EA-4E.92GQ fake-only tests. No receiver, model, process, network or GPU is used.

Passing here does not establish live or production readiness."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import pytest

from tools.hermes_core import opencode_capture_schema_v2 as schema
from tools.hermes_core import opencode_capture_entry as entry_module
from tools.hermes_core.capture_qualification_authority import (
    CaptureQualificationArtifact, SCHEMA_ID,
)
from tools.hermes_core.capture_qualification_store import CaptureQualificationStore
from tools.hermes_core.opencode_capture_entry import (
    CaptureEntryDenied, CaptureFailedClosed, OpenCodeCaptureEntry,
    ProviderCallViolation, ReceiverResult, verify_capture_v2,
)

REPO = Path(__file__).resolve().parents[2]
TASK = b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files."
NOW = "2026-10-10T00:00:01Z"
ISSUER = "capture-issuer:fake-nonlive"
MODEL = "qwen3:14b"
ISSUE_HASH = hashlib.sha256(b"fake externally reviewed issue request").hexdigest()
SSE = b'data: {"choices":[{"delta":{"content":"EA4E92_OPENCODE_CURRENT_REPLAY_OK"}}]}\n\ndata: [DONE]\n\n'


def request_body(text=TASK.decode(), **changes):
    body = {"model": MODEL, "stream": True,
            "messages": [{"role": "user", "content": text}]}
    body.update(changes)
    return json.dumps(body).encode()


def artifact(**changes):
    payload = dict(
        schema_id=SCHEMA_ID, authorization_id="cap-auth:one", issue_request_id="cap-issue:one",
        approval_id="cap-approval:one", operator_id="operator:one", run_id="cap-run:one",
        receiver_id="opencode-cli-agent", task_sha256=hashlib.sha256(TASK).hexdigest(),
        source_commit="a" * 40, executable_sha256="b" * 64, config_sha256="c" * 64,
        transport_id="d" * 64, model_binding_id="e" * 64, provider_budget_id="cap-budget:one",
        issued_at="2026-10-10T00:00:00Z", expires_at="2026-10-10T00:05:00Z",
        process_start_limit=1, nonce="nonce:one",
    )
    payload.update(changes)
    return CaptureQualificationArtifact.from_mapping(payload)


class Upstream:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, body):
        self.calls.append(body)
        if self.fail:
            raise OSError("fake upstream failure")
        return SSE


def good_result(**changes):
    args = dict(stdout=b'{"type":"text","text":"EA4E92_OPENCODE_CURRENT_REPLAY_OK"}\n',
                stderr=b"", exit_code=0, pid=4242, timed_out=False, cleanup_confirmed=True,
                stdout_complete=True, stderr_complete=True, child_process_count=0)
    args.update(changes)
    return ReceiverResult(**args)


class FakeReceiver:
    """Scripted fake. `script` is a list of (method, path, body) boundary calls."""

    def __init__(self, script=None, result=good_result(), swallow=False, raises=None,
                 terminate_raises=False):
        self.script = [("POST", "/v1/chat/completions", request_body())] if script is None else script
        self.result = result
        self.swallow, self.raises, self.terminate_raises = swallow, raises, terminate_raises
        self.runs = self.terminated = 0
        self.violations = 0

    def run(self, task, boundary):
        self.runs += 1
        assert task == TASK
        for method, path, body in self.script:
            try:
                boundary.call(method=method, path=path, body=body)
            except ProviderCallViolation:
                self.violations += 1
                if not self.swallow:
                    raise
        if self.raises:
            raise self.raises
        return self.result

    def terminate(self):
        self.terminated += 1
        if self.terminate_raises:
            raise RuntimeError("fake terminate failure")


class Env:
    def __init__(self, tmp_path, *, enabled=True, verifier="ok",
                 binding_verifier="ok", persist=True, **art):
        self.tmp = tmp_path
        self.store = CaptureQualificationStore.initialize(
            tmp_path / "cap.sqlite3", anchor_path=tmp_path / "cap.anchor.json",
            instance_id="cap-store:one")
        self.artifact = artifact(**art)
        if persist:
            self.store.persist_issued(self.artifact, issue_request_hash=ISSUE_HASH)
        self.root = tmp_path / "captures"
        self.root.mkdir()
        self.upstream = Upstream()
        verify = (lambda a, h: ISSUER) if verifier == "ok" else verifier
        verify_binding = ((lambda binding_id, model: MODEL
                           if binding_id == self.artifact.model_binding_id and model == MODEL
                           else None) if binding_verifier == "ok" else binding_verifier)
        self.entry = OpenCodeCaptureEntry(
            store=self.store, capture_root=self.root, trusted_issuer_id=ISSUER,
            clock=lambda: NOW, issuer_verifier=verify,
            binding_verifier=verify_binding, enabled=enabled)

    def run(self, receiver=None, **changes):
        a = self.artifact
        args = dict(
            artifact=a, issue_request_hash=ISSUE_HASH, task=TASK,
            expected_request_model=MODEL, receiver=receiver or FakeReceiver(),
            upstream=self.upstream, source_commit=a.source_commit,
            executable_sha256=a.executable_sha256, config_sha256=a.config_sha256,
            transport_id=a.transport_id, model_binding_id=a.model_binding_id,
            provider_budget_id=a.provider_budget_id)
        args.update(changes)
        return self.entry.run(**args)

    def consumed(self):
        return self.store.inspect(self.artifact.authorization_id).consumed


# ---------------------------------------------------------------- gating
def test_default_disabled_denies_without_consuming(tmp_path):
    env = Env(tmp_path)
    default = OpenCodeCaptureEntry(
        store=env.store, capture_root=env.root, trusted_issuer_id=ISSUER,
        clock=lambda: NOW, issuer_verifier=lambda a, h: ISSUER)
    receiver = FakeReceiver()
    args = dict(artifact=env.artifact, issue_request_hash=ISSUE_HASH, task=TASK,
                expected_request_model=MODEL, receiver=receiver, upstream=env.upstream,
                source_commit="a" * 40, executable_sha256="b" * 64, config_sha256="c" * 64,
                transport_id="d" * 64, model_binding_id="e" * 64,
                provider_budget_id="cap-budget:one")
    with pytest.raises(CaptureEntryDenied):
        default.run(**args)
    assert receiver.runs == 0 and not env.consumed() and list(env.root.iterdir()) == []


@pytest.mark.parametrize("flag", ["true", 1, "yes", None])
def test_non_boolean_enable_denied(tmp_path, flag):
    env = Env(tmp_path, enabled=flag)
    with pytest.raises(CaptureEntryDenied):
        env.run()
    assert not env.consumed()


def test_no_verifier_means_issuer_unbound(tmp_path):
    env = Env(tmp_path, verifier=None)
    receiver = FakeReceiver()
    with pytest.raises(CaptureEntryDenied, match="unbound"):
        env.run(receiver)
    assert receiver.runs == 0 and not env.consumed()


@pytest.mark.parametrize("verifier", [lambda a, h: "capture-issuer:other",
                                      lambda a, h: (_ for _ in ()).throw(RuntimeError("x"))])
def test_wrong_or_failing_issuer_denied(tmp_path, verifier):
    env = Env(tmp_path, verifier=verifier)
    with pytest.raises(CaptureEntryDenied):
        env.run()
    assert not env.consumed()


@pytest.mark.parametrize("binding_verifier", [
    None, lambda binding_id, model: "other-model",
    lambda binding_id, model: (_ for _ in ()).throw(RuntimeError("bad binding")),
])
def test_missing_wrong_or_failing_binding_verifier_denied_before_claim(tmp_path, binding_verifier):
    env = Env(tmp_path, binding_verifier=binding_verifier)
    receiver = FakeReceiver()
    with pytest.raises(CaptureEntryDenied):
        env.run(receiver)
    assert receiver.runs == 0 and not env.consumed() and list(env.root.iterdir()) == []


def test_caller_cannot_substitute_nemotron_for_authorized_request_model(tmp_path):
    env = Env(tmp_path)
    receiver = FakeReceiver()
    with pytest.raises(CaptureEntryDenied, match="authorized binding"):
        env.run(receiver, expected_request_model="nemotron-3-ultra-free")
    assert receiver.runs == 0 and not env.consumed() and list(env.root.iterdir()) == []


def test_unissued_cancelled_revoked_and_foreign_authority_denied(tmp_path):
    (tmp_path / "a").mkdir()
    env = Env(tmp_path / "a", persist=False)
    with pytest.raises(CaptureEntryDenied):
        env.run()
    (tmp_path / "b").mkdir()
    env = Env(tmp_path / "b")
    env.store.cancel(env.artifact.authorization_id, at=NOW)
    with pytest.raises(CaptureEntryDenied):
        env.run()
    (tmp_path / "c").mkdir()
    env = Env(tmp_path / "c")
    env.store.revoke(env.artifact.authorization_id, at=NOW)
    with pytest.raises(CaptureEntryDenied):
        env.run()
    (tmp_path / "d").mkdir()
    env = Env(tmp_path / "d")
    with pytest.raises(CaptureEntryDenied):  # production-style dict is not a capture artifact
        env.run(artifact={"invocation_authorization_id": "x", "runtime_scope": "production"})


@pytest.mark.parametrize("change", [
    {"task": b"different task"}, {"source_commit": "f" * 40},
    {"executable_sha256": "f" * 64}, {"config_sha256": "f" * 64},
    {"transport_id": "f" * 64}, {"model_binding_id": "f" * 64},
    {"provider_budget_id": "other"}, {"receiver_id": "kilo-cli-agent"},
])
def test_wrong_identity_denied_before_start_and_not_consumed(tmp_path, change):
    env = Env(tmp_path)
    receiver = FakeReceiver()
    with pytest.raises(CaptureEntryDenied):
        env.run(receiver, **change)
    assert receiver.runs == 0 and not env.consumed() and list(env.root.iterdir()) == []


def test_replay_denied_after_success_and_no_refund_after_failure(tmp_path):
    env = Env(tmp_path)
    env.run()
    again = FakeReceiver()
    with pytest.raises(CaptureEntryDenied):
        env.run(again)
    assert again.runs == 0
    env2_path = tmp_path / "f"
    env2_path.mkdir()
    env2 = Env(env2_path)
    env2.upstream = Upstream(fail=True)
    with pytest.raises(CaptureFailedClosed):
        env2.run()
    assert env2.consumed()
    with pytest.raises(CaptureEntryDenied):
        env2.run(FakeReceiver())


# ---------------------------------------------------------------- happy path + schema
def test_single_call_capture_is_durable_labeled_and_verifiable(tmp_path):
    env = Env(tmp_path)
    receiver = FakeReceiver()
    result = env.run(receiver)
    m = result.manifest
    assert result.status == "COMPLETE" and receiver.runs == 1 and env.consumed()
    assert len(env.upstream.calls) == 1 and env.upstream.calls[0] == request_body()
    assert m["capture_class"] == "FRESH_CURRENT_QUALIFICATION"
    assert m["historical_capture"] == "NO"
    assert m["issuer_id"] == ISSUER
    assert m["execution_origin"] == "FAKE_INJECTED_NONLIVE" and m["acceptance_eligible"] == "NO"
    assert m["process_start_count_observed"] == 1 and m["provider_call_count_forwarded"] == 1
    assert m["auxiliary_call_count"] == 0 and m["denied_call_count"] == 0
    assert m["model_binding_id"] == env.artifact.model_binding_id
    assert m["gpu_policy_status"] == "UNRESOLVED_PREREQUISITE" and m["cpu_only_proven"] == "NO"
    assert "GPU_CPU_ONLY_UNPROVEN" in m["unresolved_prerequisites"]
    d = result.directory
    assert (d / "request-1.bin").read_bytes() == request_body()
    assert (d / "response-1.bin").read_bytes() == SSE
    assert (d / "stdout.bin").read_bytes() == good_result().stdout
    assert (d / "authorization.json").read_bytes() == env.artifact.canonical_bytes()
    assert verify_capture_v2(d) == m
    assert m["claimed_at"] <= m["started_at"] <= m["ended_at"]


def test_existing_capture_never_overwritten(tmp_path):
    env = Env(tmp_path)
    result = env.run()
    with pytest.raises(FileExistsError):
        entry_module._write_new(result.directory / "stdout.bin", b"x")


def test_verify_detects_tamper(tmp_path):
    env = Env(tmp_path)
    d = env.run().directory
    (d / "stdout.bin").write_bytes(b"tampered")
    with pytest.raises(schema.CaptureSchemaError):
        verify_capture_v2(d)
    env2_path = tmp_path / "t2"
    env2_path.mkdir()
    d2 = Env(env2_path).run().directory
    manifest = json.loads((d2 / "manifest.json").read_text())
    manifest["pid"] = 7
    (d2 / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    with pytest.raises(schema.CaptureSchemaError):
        verify_capture_v2(d2)


def test_schema_is_frozen():
    assert len(schema.MANIFEST_FIELDS) == 46
    assert schema.SCHEMA_FINGERPRINT == "1b72dffd0a0ce71585315b1ea40762a0479911552fb40475884f1a1f49c2947f"


def valid_manifest(tmp_path):
    return Env(tmp_path).run().manifest


@pytest.mark.parametrize("key,value", [
    ("capture_class", "HISTORICAL"), ("historical_capture", "YES"),
    ("execution_origin", "LIVE"), ("acceptance_eligible", "YES"),
    ("gpu_policy_status", "RESOLVED"), ("cpu_only_proven", "YES"),
    ("issuer_verification", "SIGNED"), ("unresolved_prerequisites", []),
    ("schema_id", "hermes.opencode-capture-manifest/v1"),
    ("provider_call_count_forwarded", 2), ("auxiliary_call_count", 1),
    ("process_start_count_observed", 2), ("exit_code", 1),
])
def test_validator_rejects_relabel_or_contradiction(tmp_path, key, value):
    m = dict(valid_manifest(tmp_path))
    m[key] = value
    with pytest.raises(schema.CaptureSchemaError):
        schema.validate_manifest(m)


def test_validator_rejects_extra_and_missing_keys(tmp_path):
    m = dict(valid_manifest(tmp_path))
    with pytest.raises(schema.CaptureSchemaError):
        schema.validate_manifest({**m, "extra": 1})
    m.pop("pid")
    with pytest.raises(schema.CaptureSchemaError):
        schema.validate_manifest(m)


# ---------------------------------------------------------------- one-call enforcement
def failed(env, receiver):
    with pytest.raises(CaptureFailedClosed) as info:
        env.run(receiver)
    return info.value.result.manifest


def test_second_provider_call_denied_before_upstream_and_fails_closed(tmp_path):
    env = Env(tmp_path)
    body = request_body()
    receiver = FakeReceiver(script=[("POST", "/v1/chat/completions", body)] * 2)
    m = failed(env, receiver)
    assert len(env.upstream.calls) == 1
    assert "SECOND_CALL" in m["failure_reasons"] and receiver.terminated == 1
    assert m["provider_call_count_forwarded"] == 1 and m["denied_call_count"] == 1
    assert m["capture_status"] == "FAILED_CLOSED" and env.consumed()
    verify_capture_v2(tmp_path / "captures" / next((tmp_path / "captures").iterdir()).name)


def test_violation_fails_even_if_receiver_swallows_denial(tmp_path):
    env = Env(tmp_path)
    receiver = FakeReceiver(script=[("POST", "/v1/chat/completions", request_body())] * 3, swallow=True)
    m = failed(env, receiver)
    assert receiver.violations == 2 and len(env.upstream.calls) == 1
    assert m["denied_call_count"] == 2 and receiver.terminated == 1


def test_auxiliary_title_call_first_is_denied_and_never_forwarded(tmp_path):
    env = Env(tmp_path)
    title = request_body("Generate a short title for this conversation")
    receiver = FakeReceiver(script=[("POST", "/v1/chat/completions", title),
                                    ("POST", "/v1/chat/completions", request_body())], swallow=True)
    m = failed(env, receiver)
    assert env.upstream.calls == [request_body()]
    assert "AUXILIARY_NON_TASK" in m["failure_reasons"]
    assert m["auxiliary_call_count"] == 1 and m["provider_calls"][0]["forwarded"] is False


@pytest.mark.parametrize("call,reason", [
    (("POST", "/v1/models", b"{}"), "AUXILIARY_ROUTE"),
    (("GET", "/v1/chat/completions", b""), "AUXILIARY_ROUTE"),
    (("POST", "/v1/chat/completions", request_body(model="other")), "INVALID_REQUEST"),
    (("POST", "/v1/chat/completions", request_body(stream=False)), "INVALID_REQUEST"),
    (("POST", "/v1/chat/completions", b"not json"), "INVALID_REQUEST"),
    (("POST", "/v1/chat/completions", b'{"model":"qwen3:14b","model":"x"}'), "INVALID_REQUEST"),
    (("POST", "/v1/chat/completions", b"x" * 70000), "INVALID_REQUEST"),
])
def test_out_of_scope_calls_denied_without_forwarding(tmp_path, call, reason):
    env = Env(tmp_path)
    receiver = FakeReceiver(script=[call], swallow=True)
    m = failed(env, receiver)
    assert env.upstream.calls == [] and reason in m["failure_reasons"]
    assert "PROVIDER_CALL_COUNT_NOT_ONE" in m["failure_reasons"]


def test_zero_provider_calls_is_not_a_success(tmp_path):
    env = Env(tmp_path)
    m = failed(env, FakeReceiver(script=[]))
    assert m["failure_reasons"] == ["PROVIDER_CALL_COUNT_NOT_ONE"]


def test_upstream_failure_keeps_credit_and_fails_closed(tmp_path):
    env = Env(tmp_path)
    env.upstream = Upstream(fail=True)
    m = failed(env, FakeReceiver(swallow=True))
    assert "UPSTREAM_OR_RESPONSE_CAPTURE_FAILED" in m["failure_reasons"]
    assert env.consumed() and len(env.upstream.calls) == 1


def test_terminate_failure_is_recorded(tmp_path):
    env = Env(tmp_path)
    receiver = FakeReceiver(script=[("POST", "/v1/models", b"{}")], swallow=True, terminate_raises=True)
    assert "TERMINATE_FAILED" in failed(env, receiver)["failure_reasons"]


def test_concurrent_calls_forward_exactly_once(tmp_path):
    env = Env(tmp_path)

    class Racer(FakeReceiver):
        def run(self, task, boundary):
            def one(_):
                try:
                    boundary.call(method="POST", path="/v1/chat/completions", body=request_body())
                    return 1
                except ProviderCallViolation:
                    return 0
            with ThreadPoolExecutor(8) as pool:
                assert sum(pool.map(one, range(8))) == 1
            return self.result

    m = failed(env, Racer())
    assert len(env.upstream.calls) == 1 and m["denied_call_count"] == 7


# ---------------------------------------------------------------- process accounting
@pytest.mark.parametrize("changes,reason", [
    ({"exit_code": 3}, "NONZERO_EXIT"), ({"timed_out": True}, "TIMED_OUT"),
    ({"cleanup_confirmed": False}, "CLEANUP_NOT_CONFIRMED"),
    ({"stdout_complete": False}, "STREAM_INCOMPLETE"),
    ({"stderr_complete": False}, "STREAM_INCOMPLETE"),
    ({"stdout": b""}, "EMPTY_STDOUT"),
    ({"child_process_count": 2}, "CHILD_PROCESSES_OBSERVED"),
])
def test_process_accounting_failures_fail_closed(tmp_path, changes, reason):
    env = Env(tmp_path)
    m = failed(env, FakeReceiver(result=good_result(**changes)))
    assert reason in m["failure_reasons"] and env.consumed()


@pytest.mark.parametrize("bad", [None, "x", good_result(pid=0), good_result(pid=True),
                                 good_result(stdout="text")])
def test_invalid_receiver_result_fails_closed(tmp_path, bad):
    env = Env(tmp_path)
    m = failed(env, FakeReceiver(result=bad))
    assert "INVALID_RECEIVER_RESULT" in m["failure_reasons"]


def test_receiver_exception_terminates_and_fails_closed(tmp_path):
    env = Env(tmp_path)
    receiver = FakeReceiver(raises=RuntimeError("boom"))
    m = failed(env, receiver)
    assert "RECEIVER_EXCEPTION:RuntimeError" in m["failure_reasons"] and receiver.terminated == 1


# ---------------------------------------------------------------- isolation / not wired
FORBIDDEN_IMPORTS = {"subprocess", "socket", "http", "urllib", "requests", "ctypes",
                     "multiprocessing", "asyncio", "ssl", "shutil"}
FORBIDDEN_TOKENS = ("opencode_live_binding", "OpenCodeLiveBindingHarness", "ProductionActivation",
                    "production_activation", "opencode_adapter", "os.system", "Popen", "ollama",
                    "CUDA", "gpu_enabled")


@pytest.mark.parametrize("name", ["opencode_capture_entry.py", "opencode_capture_schema_v2.py"])
def test_modules_have_no_launcher_network_or_production_capability(name):
    source = (REPO / "tools" / "hermes_core" / name).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & FORBIDDEN_IMPORTS
    code_only = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for token in FORBIDDEN_TOKENS:
        # docstring prose may name forbidden components; code must not reference them
        assert token not in "\n".join(
            n.id if isinstance(n, ast.Name) else getattr(n, "attr", "")
            for n in ast.walk(tree) if isinstance(n, (ast.Name, ast.Attribute))
        ), token
    assert code_only


def test_entry_is_not_wired_into_production():
    needles = ("opencode_capture_entry", "opencode_capture_schema_v2")
    scanned = [REPO / "app.py"] + [
        p for p in (REPO / "tools").rglob("*.py")
        if p.name not in ("opencode_capture_entry.py", "opencode_capture_schema_v2.py")
    ]
    hits = [str(p) for p in scanned if p.is_file()
            and any(n in p.read_text(encoding="utf-8", errors="ignore") for n in needles)]
    assert hits == []
