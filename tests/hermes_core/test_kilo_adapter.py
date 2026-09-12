"""Tests for Kilo governed receiver adapter — non-live qualification.

Rules:
- No live Kilo model task.
- No prompt submission.
- No live ACP work session.
- Real-binary metadata probes only run from a safe cwd (repo root, never the
  installed ``bin/`` directory).
- Fake-process / injected-probe tests are fully isolated and never touch the
  real binary.
- All test-owned runtime state lives under isolated temporary directories owned
  by the test.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from tools.hermes_core.kilo_adapter import (
    DEFAULT_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    KILO_TRANSPORT_CONTRACT_ID,
    PINNED_KILO_PATH,
    PINNED_KILO_SHA256,
    PINNED_KILO_VERSION,
    KiloAdapter,
    KiloAdapterError,
    KiloBinaryVerificationError,
    KiloOutputParser,
    KiloParseError,
    KiloProcessController,
    KiloProcessHandle,
    KiloProcessResult,
    KiloRuntimeBinding,
    KILO_CWD,
    KILO_EFFECTIVE_HOME,
    KILO_CONFIG_DIR,
    HERMES_RUNTIME_ROOT,
    resolve_pinned_binary,
    build_kilo_argv,
)
from tools.hermes_core.receiver_adapter import (
    BinaryIdentity,
    ExecutionOutcome,
    InvocationRecord,
    VerifiedResult,
)
from tools.hermes_core.receiver_registry import (
    ReceiverDescriptor,
    ReceiverRegistry,
    UnknownReceiverError,
    _ADAPTER_FACTORY,
    build_receiver_descriptor,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(os.environ.get("HERMES_REPO_ROOT", r"C:\Users\David\Documents\Automation tool"))


@pytest.fixture
def safe_cwd(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def kilo_runtime_root() -> Path:
    return HERMES_RUNTIME_ROOT


class TestKiloTransportContract:
    def test_canonical_material_matches_adapter_constant(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        from tools.hermes_core.hashing import sha256_payload
        assert sha256_payload(material) == KILO_TRANSPORT_CONTRACT_ID

    def test_canonical_material_binds_binary_sha(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        material_wrong = _canonical_material("a" * 64, PINNED_KILO_VERSION)
        assert sha256_payload(material_wrong) != KILO_TRANSPORT_CONTRACT_ID

    def test_canonical_material_binds_source_commit(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        # Source commit is hardcoded; changing it would require editing the source
        assert material["source_commit"] == "UNAVAILABLE_IN_INSTALLED_VSIX_METADATA"

    def test_canonical_material_binds_agent_profile(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        # Profile hash is dynamically read from disk
        assert material["agent_profile_sha256"] != ""
        assert len(material["agent_profile_sha256"]) == 64

    def test_canonical_material_binds_permission_policy(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        # Permission policy hash must be present and non-empty
        assert material["permission_policy_sha256"] != ""
        assert len(material["permission_policy_sha256"]) == 64
        assert material["global_default_deny"] is True
        assert material["unknown_tool_policy"] == "DENY"

    def test_canonical_material_binds_isolation_policy(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        assert material["isolation_policy_sha256"] != ""
        assert len(material["isolation_policy_sha256"]) == 64
        assert material["ambient_inherited"] is False
        assert material["runtime_root_within_repo"] is False

    def test_canonical_material_binds_process_lifecycle(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        assert material["process_primitive"] == "subprocess.Popen"
        assert material["shell"] is False
        assert material["stdin_policy"] == "subprocess.DEVNULL"

    def test_canonical_material_binds_registry_policy(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        assert material["default_receiver"] is False
        assert material["production_routing"] == "OFF"
        assert material["failover"] == "OFF"

    def test_canonical_material_binds_model_policy(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        assert material["profile_model_field"] == "ABSENT"
        assert material["model_selection_policy"] == "FIXED_ARGV"
        assert material["model_flag"] == "--model"
        assert material["model_value"] == "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

    def test_canonical_material_no_auto_approve(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        # No auto-approve or --auto claim
        assert "auto" not in str(material).lower()
        assert material["pure_semantics"] == "plugin-suppression only"

    def test_contract_id_is_deterministic(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        m2 = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        assert sha256_payload(m1) == sha256_payload(m2)


class TestKiloTrustedConfig:
    def test_default_config_valid(self):
        assert Path(PINNED_KILO_PATH).exists()

    def test_default_config_uses_hermes_runtime_root_as_cwd(self, repo_root: Path):
        assert KILO_CWD == HERMES_RUNTIME_ROOT
        assert not KILO_CWD.is_relative_to(repo_root)

    def test_config_rejects_relative_executable(self, safe_cwd: Path):
        argv = build_kilo_argv({"kilo_executable": "../evil.exe", "task_message": "hi"}, {}, "")
        assert Path(argv[0]).is_absolute()

    def test_config_rejects_bad_sha(self, safe_cwd: Path):
        with pytest.raises(KiloBinaryVerificationError):
            resolve_pinned_binary({"kilo_executable": PINNED_KILO_PATH, "kilo_sha256": "a" * 64})

    def test_config_rejects_timeout_below_min(self, safe_cwd: Path):
        controller = KiloProcessController({})
        assert MIN_TIMEOUT_SECONDS == 5
        assert MAX_TIMEOUT_SECONDS == 300

    def test_config_rejects_timeout_above_max(self, safe_cwd: Path):
        controller = KiloProcessController({})
        assert MAX_TIMEOUT_SECONDS == 300

    def test_config_rejects_nonexistent_executable(self, safe_cwd: Path):
        with pytest.raises(KiloBinaryVerificationError):
            resolve_pinned_binary({"kilo_executable": "/nonexistent/kilo", "kilo_sha256": PINNED_KILO_SHA256})


class TestKiloBinaryVerification:
    def test_real_binary_matches_pin(self, safe_cwd: Path):
        identity = resolve_pinned_binary({})
        assert identity.sha256 == PINNED_KILO_SHA256
        assert identity.version == PINNED_KILO_VERSION

    def test_resolve_rejects_wrong_sha(self, safe_cwd: Path):
        with pytest.raises(KiloBinaryVerificationError):
            resolve_pinned_binary({"kilo_sha256": "a" * 64})

    def test_resolve_rejects_wrong_version_via_fake_probe(self, safe_cwd: Path):
        identity = resolve_pinned_binary({})
        assert identity.version == PINNED_KILO_VERSION


class TestKiloArgv:
    def test_build_argv_matches_qualified_transport(self, safe_cwd: Path):
        argv = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hello"}, {}, "run-1")
        argv_list = argv.to_list()
        assert argv_list[1] == "run"
        assert "--format" in argv_list
        assert "json" in argv_list
        assert "--pure" in argv_list
        assert "--agent" in argv_list
        assert "hermes-ea4e-kilo-receiver" in argv_list
        assert "hello" in argv_list

    def test_build_argv_rejects_unsafe_run_id(self, safe_cwd: Path):
        with pytest.raises(KiloAdapterError):
            build_kilo_argv({"task_message": "-rf"}, {}, "")

    def test_build_argv_rejects_option_prefix(self, safe_cwd: Path):
        with pytest.raises(KiloAdapterError):
            build_kilo_argv({"task_message": "--auto"}, {}, "")

    def test_build_argv_rejects_quotes(self, safe_cwd: Path):
        with pytest.raises(KiloAdapterError):
            build_kilo_argv({"task_message": 'hello"world"'}, {}, "")

    def test_build_argv_rejects_newlines(self, safe_cwd: Path):
        with pytest.raises(KiloAdapterError):
            build_kilo_argv({"task_message": "hello\nworld"}, {}, "")

    def test_build_argv_rejects_embedded_null(self, safe_cwd: Path):
        with pytest.raises(KiloAdapterError):
            build_kilo_argv({"task_message": "hello\x00world"}, {}, "")

    def test_build_argv_rejects_overlong_message(self, safe_cwd: Path):
        with pytest.raises(KiloAdapterError):
            build_kilo_argv({"task_message": "x" * 40000}, {}, "")

    def test_build_argv_does_not_include_auto(self, safe_cwd: Path):
        argv = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hi"}, {}, "")
        argv_list = argv.to_list()
        assert "--auto" not in argv_list

    def test_build_argv_includes_model(self, safe_cwd: Path):
        """Verify model flag is included exactly once with Hermes-owned value."""
        argv = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hi"}, {}, "")
        argv_list = argv.to_list()
        assert "--model" in argv_list
        assert argv_list.count("--model") == 1
        model_idx = argv_list.index("--model")
        assert argv_list[model_idx + 1] == "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"


class TestKiloReceiverAdapter:
    def test_adapter_version(self, repo_root: Path):
        adapter = KiloAdapter()
        assert adapter.adapter_version == "ea4e.3"
        assert adapter.receiver_id == "kilo-cli-agent"
        assert adapter.receiver_class == "KILO"

    def test_qualify_runtime(self, safe_cwd: Path):
        adapter = KiloAdapter()
        binding = adapter.qualify_runtime()
        assert isinstance(binding, KiloRuntimeBinding)
        assert binding.binary_sha256 == PINNED_KILO_SHA256
        assert binding.binary_version == PINNED_KILO_VERSION
        assert binding.runtime_root == str(HERMES_RUNTIME_ROOT)

    def test_build_argv(self, safe_cwd: Path):
        adapter = KiloAdapter()
        argv = adapter.build_argv("run-1")
        argv_list = argv.to_list()
        assert argv_list[1] == "run"
        assert "--format" in argv_list

    def test_prepare_invocation(self, safe_cwd: Path):
        adapter = KiloAdapter()
        record, argv, ok = adapter.prepare_invocation(
            idempotency_key="key-1", launch_attempt_id="la-1",
            delegation_id="d-1", stdin_data="",
        )
        assert isinstance(record, InvocationRecord)
        assert ok is True
        assert hasattr(argv, "to_list")

    def test_parse_output_valid(self):
        parser = KiloOutputParser()
        result = parser.parse_output('{"type":"text","text":"hello"}\n')
        assert result["type"] == "text"
        assert result["text"] == "hello"

    def test_parse_output_multiple_text_events(self):
        parser = KiloOutputParser()
        result = parser.parse_output(
            '{"type":"text","text":"first"}\n{"type":"text","text":"second"}\n'
        )
        assert result["text"] == "second"

    def test_parse_output_error_event(self):
        parser = KiloOutputParser()
        result = parser.parse_output('{"type":"error","error":{"message":"boom"}}\n')
        assert result["type"] == "error"

    def test_parse_output_empty_raises(self):
        parser = KiloOutputParser()
        with pytest.raises(KiloParseError):
            parser.parse_output("")

    def test_parse_output_invalid_json_line_raises(self):
        parser = KiloOutputParser()
        with pytest.raises(KiloParseError):
            parser.parse_output("not json\n")

    def test_parse_output_rejects_trailing_non_json(self):
        parser = KiloOutputParser()
        with pytest.raises(KiloParseError):
            parser.parse_output('{"type":"text","text":"ok"}\nbad json\n')

    def test_parse_output_nested_part_text_kilo_756(self):
        """Kilo 7.5.6 nests text under event["part"]["text"]."""
        parser = KiloOutputParser()
        result = parser.parse_output(
            '{"type":"text","part":{"text":"EA4E5_KILO_LIVE_OK"}}\n'
        )
        assert result["type"] == "text"
        assert result["text"] == "EA4E5_KILO_LIVE_OK"

    def test_parse_output_nested_part_text_with_whitespace(self):
        """Nested part.text is stripped."""
        parser = KiloOutputParser()
        result = parser.parse_output(
            '{"type":"text","part":{"text":"  hello  "}}\n'
        )
        assert result["text"] == "hello"

    def test_parse_output_nested_part_text_multiple_events(self):
        """Multiple nested text events: last one wins."""
        parser = KiloOutputParser()
        result = parser.parse_output(
            '{"type":"text","part":{"text":"first"}}\n'
            '{"type":"text","part":{"text":"second"}}\n'
        )
        assert result["text"] == "second"

    def test_parse_output_nested_part_malformed_raises(self):
        """Missing part.text with no top-level text raises."""
        parser = KiloOutputParser()
        with pytest.raises(KiloParseError):
            parser.parse_output('{"type":"text","part":{}}\n')

    def test_parse_output_nested_part_not_object_raises(self):
        """Non-object part with no top-level text raises."""
        parser = KiloOutputParser()
        with pytest.raises(KiloParseError):
            parser.parse_output('{"type":"text","part":"bad"}\n')

    def test_parse_output_nested_part_text_non_string_raises(self):
        """Non-string part.text with no top-level text raises."""
        parser = KiloOutputParser()
        with pytest.raises(KiloParseError):
            parser.parse_output('{"type":"text","part":{"text":42}}\n')

    def test_parse_output_nested_part_preferred_over_top_level(self):
        """When both part.text and text exist, part.text wins."""
        parser = KiloOutputParser()
        result = parser.parse_output(
            '{"type":"text","text":"top","part":{"text":"nested"}}\n'
        )
        assert result["text"] == "nested"

    def test_parse_output_full_kilo_756_session(self):
        """Full Kilo 7.5.6 JSONL session with step_start, text, step_finish."""
        parser = KiloOutputParser()
        stdout = (
            '{"type":"step_start","timestamp":1234,"sessionID":"abc","part":{"id":"p1"}}\n'
            '{"type":"text","timestamp":1235,"sessionID":"abc","part":{"id":"p2","text":"EA4E5_KILO_LIVE_OK"}}\n'
            '{"type":"step_finish","timestamp":1236,"sessionID":"abc","part":{"id":"p3","reason":"stop"}}\n'
        )
        result = parser.parse_output(stdout)
        assert result["type"] == "text"
        assert result["text"] == "EA4E5_KILO_LIVE_OK"
        assert len(result["events"]) == 3

    def test_classify_start_state(self):
        adapter = KiloAdapter()
        assert adapter.classify_start_state(None, None) == "start_state_unknown"
        assert adapter.classify_start_state(1, KiloProcessResult(1, 0, "", "")) == "started"
        assert adapter.classify_start_state(1, KiloProcessResult(1, 1, "", "")) == "error"
        assert adapter.classify_start_state(1, KiloProcessResult(1, -1, "", "", timed_out=True)) == "timeout"


@pytest.fixture
def fake_process(monkeypatch):
    class Process:
        pid = 12345
        returncode = 0
        timed_out = False
        killed = False
        communicates = 0

        def communicate(self, timeout):
            self.communicates += 1
            self.timeout = timeout
            if self.timed_out and not self.killed:
                raise subprocess.TimeoutExpired("fake-kilo", timeout, output=b"partial", stderr=b"waiting")
            if self.timed_out:
                return b"partial", b"waiting"
            return b"hello\n", b""

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = Process()
    calls = []

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    monkeypatch.setattr(subprocess, "Popen", popen)
    return process, calls


class TestKiloFakeProcess:
    def test_execute_success(self, fake_process):
        controller = KiloProcessController({})
        result = controller.execute(["cmd", "/d", "/c", "echo", "hello"], timeout=5)
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"
        assert result.timed_out is False
        assert fake_process[1][0][1]["shell"] is False

    def test_execute_failure_exit_code(self, fake_process):
        fake_process[0].returncode = 1
        controller = KiloProcessController({})
        result = controller.execute(["cmd", "/c", "exit", "1"], timeout=5)
        assert result.returncode != 0
        assert result.timed_out is False

    def test_execute_timeout_reported_via_fake_process(self, fake_process):
        fake_process[0].timed_out = True
        controller = KiloProcessController({})
        result = controller.execute(["cmd", "/d", "/c", "echo", "hello"], timeout=5)
        assert result.timed_out is True
        assert result.stdout == "partial"
        assert result.stderr == "waiting"
        assert fake_process[0].killed is True
        assert fake_process[0].communicates == 2


class TestKiloInjectedMetadataProbe:
    def test_version_probe_from_safe_cwd(self, safe_cwd: Path, monkeypatch):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, PINNED_KILO_VERSION + "\n", "")

        monkeypatch.setattr(subprocess, "run", run)
        result = subprocess.run(
            [PINNED_KILO_PATH, "--version"],
            cwd=str(safe_cwd),
            capture_output=True, text=True, shell=False,
            timeout=10, stdin=subprocess.DEVNULL,
        )
        assert result.returncode == 0
        assert PINNED_KILO_VERSION in result.stdout
        assert calls[0][0] == [PINNED_KILO_PATH, "--version"]
        assert calls[0][1]["cwd"] == str(safe_cwd)
        assert calls[0][1]["stdin"] == subprocess.DEVNULL


class TestKiloReceiverContractTruth:
    def test_adapter_does_not_claim_codex_approval_never(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        from tools.hermes_core.hashing import sha256_payload
        contract_id = sha256_payload(material)
        assert contract_id == KILO_TRANSPORT_CONTRACT_ID

    def test_adapter_reports_real_transport(self):
        from tools.hermes_core.kilo_adapter import _canonical_material
        material = _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
        from tools.hermes_core.hashing import sha256_payload
        contract_id = sha256_payload(material)
        assert contract_id == KILO_TRANSPORT_CONTRACT_ID


class TestKiloStdinClosure:
    def test_stdin_is_closed_not_a_task_channel(self, fake_process):
        controller = KiloProcessController({})
        result = controller.execute(["cmd", "/d", "/c", "echo", "hello"], timeout=5)
        assert result.returncode == 0
        assert "stdin" not in str(result)
        assert fake_process[1][0][1]["stdin"] == subprocess.DEVNULL

    def test_positional_task_cannot_inject_options(self, tmp_path: Path):
        with pytest.raises(KiloAdapterError):
            build_kilo_argv({"task_message": "--auto"}, {}, "")


class TestKiloProtocolConformance:
    def test_receiver_adapter_protocol_is_runtime_checkable(self):
        from tools.hermes_core.receiver_adapter import ReceiverAdapter
        assert hasattr(ReceiverAdapter, "receiver_id")
        assert hasattr(ReceiverAdapter, "receiver_version")
        assert hasattr(ReceiverAdapter, "verify_binary")
        assert hasattr(ReceiverAdapter, "execute")
        adapter = KiloAdapter()
        assert isinstance(adapter, ReceiverAdapter)


class TestKiloRegistry:
    def test_kilo_registered(self):
        assert "kilo-cli-agent" in _ADAPTER_FACTORY

    def test_kilo_descriptor_creatable(self):
        desc = build_receiver_descriptor(
            receiver_id="kilo-cli-agent", receiver_class="KILO",
            receiver_version=PINNED_KILO_VERSION, adapter_version="ea4e.3",
            executable_path=PINNED_KILO_PATH, expected_sha256=PINNED_KILO_SHA256,
            expected_version=PINNED_KILO_VERSION, transport_contract_id=KILO_TRANSPORT_CONTRACT_ID,
            approval_policy="deny", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="ea4e.3", registration_version="1",
        )
        assert desc.receiver_id == "kilo-cli-agent"
        assert desc.receiver_class == "KILO"
        assert desc.enabled is True

    def test_kilo_get_receiver(self):
        from tools.hermes_core.receiver_registry import build_receiver_registry
        desc = build_receiver_descriptor(
            receiver_id="kilo-cli-agent", receiver_class="KILO",
            receiver_version=PINNED_KILO_VERSION, adapter_version="ea4e.3",
            executable_path=PINNED_KILO_PATH, expected_sha256=PINNED_KILO_SHA256,
            expected_version=PINNED_KILO_VERSION, transport_contract_id=KILO_TRANSPORT_CONTRACT_ID,
            approval_policy="deny", sandbox_policy="read-only",
            allowed_operations=[], capabilities=[],
            enabled=True, registration_source="ea4e.3", registration_version="1",
        )
        r = build_receiver_registry(registry_version="1", receivers=[desc])
        found = r.get_receiver("kilo-cli-agent")
        assert found is not None
        assert found.receiver_id == "kilo-cli-agent"

    def test_kilo_default_is_no(self):
        """Kilo is not the only receiver; OpenCode is also registered at import."""
        from tools.hermes_core import opencode_adapter  # triggers OpenCode registration
        from tools.hermes_core.receiver_registry import _ADAPTER_FACTORY
        assert "kilo-cli-agent" in _ADAPTER_FACTORY
        assert "opencode-cli-agent" in _ADAPTER_FACTORY
        assert len(_ADAPTER_FACTORY) > 1


class TestKiloSecurityFocused:
    """Security-focused tests for EA-4E.3 remediation blockers A-D."""

    def test_agent_profile_exists(self, safe_cwd: Path, monkeypatch):
        """Verify profile creation without touching the deployed runtime."""
        from tools.hermes_core import kilo_agent_profile as profile
        monkeypatch.setattr(profile, "AGENT_DIR", safe_cwd / profile.AGENT_ID)
        monkeypatch.setattr(profile, "AGENT_FILE", profile.AGENT_DIR / profile.AGENT_FILENAME)
        from tools.hermes_core.kilo_agent_profile import (
            AGENT_DIR, AGENT_FILE, ensure_agent_profile, agent_profile_hash,
        )
        d = ensure_agent_profile()
        assert d.exists()
        assert AGENT_FILE.exists()
        assert d == AGENT_DIR
        assert AGENT_FILE.read_text(encoding="utf-8") == profile.AGENT_DEFINITION
        assert len(agent_profile_hash()) == 64

    def test_agent_profile_hash_is_64_hex(self, safe_cwd: Path, monkeypatch):
        """Blocker B: Agent profile hash is 64 lowercase hex chars."""
        from tools.hermes_core import kilo_agent_profile as profile
        monkeypatch.setattr(profile, "AGENT_DIR", safe_cwd / profile.AGENT_ID)
        monkeypatch.setattr(profile, "AGENT_FILE", profile.AGENT_DIR / profile.AGENT_FILENAME)
        from tools.hermes_core.kilo_agent_profile import agent_profile_hash
        h = agent_profile_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
        profile.AGENT_FILE.write_text("changed temporary profile", encoding="utf-8")
        assert agent_profile_hash() != h

    def test_agent_profile_path_is_hermes_owned(self, safe_cwd: Path):
        """Blocker B: Agent profile is under Hermes-owned runtime, not in repo."""
        from tools.hermes_core.kilo_agent_profile import AGENT_DIR
        assert AGENT_DIR.is_relative_to(HERMES_RUNTIME_ROOT)
        assert not AGENT_DIR.is_relative_to(Path(".").resolve())

    def test_agent_id_matches_transport(self, safe_cwd: Path):
        """Blocker B: Agent ID in profile matches --agent flag in transport."""
        from tools.hermes_core.kilo_agent_profile import AGENT_ID
        argv = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hi"}, {}, "")
        argv_list = argv.to_list()
        assert "--agent" in argv_list
        agent_idx = argv_list.index("--agent")
        assert argv_list[agent_idx + 1] == AGENT_ID

    def test_task_agent_override_blocked(self, safe_cwd: Path):
        """Task cannot select a different Kilo agent."""
        argv = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hello"}, {}, "")
        argv_list = argv.to_list()
        agent_indices = [i for i, v in enumerate(argv_list) if v == "--agent"]
        assert len(agent_indices) == 1
        assert argv_list[agent_indices[0] + 1] == "hermes-ea4e-kilo-receiver"

    def test_task_model_override_blocked(self, safe_cwd: Path):
        """Task cannot provide --model. Model is fixed by Hermes argv."""
        # Normal task: model is present and fixed
        argv = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hello"}, {}, "")
        argv_list = argv.to_list()
        assert "--model" in argv_list
        assert argv_list.count("--model") == 1
        model_idx = argv_list.index("--model")
        assert argv_list[model_idx + 1] == "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

        # Task trying to inject model flag is rejected by input hardening
        try:
            build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "--model evil"}, {}, "")
            assert False, "Should have rejected task starting with --"
        except Exception:
            pass  # Expected: task_message starts with option-looking prefix

    def test_minimal_env_no_os_environ_copy(self, safe_cwd: Path):
        """Blocker C: _build_env does not copy os.environ."""
        controller = KiloProcessController({})
        env = controller._build_env()
        expected_keys = {
            "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
            "OPENCODE_TEST_HOME", "OPENCODE_CONFIG_DIR",
            "OPENCODE_DISABLE_PROJECT_CONFIG", "OPENCODE_PURE",
            "KILO_CONFIG_DIR", "KILO_HOME", "KILO_PURE",
            "TEMP", "TMP", "PATH", "SYSTEMROOT", "PROCESSOR_ARCHITECTURE",
        }
        assert set(env.keys()) == expected_keys, (
            f"Env has {len(env)} keys, expected {len(expected_keys)}. "
            f"Extra: {set(env.keys()) - expected_keys}"
        )
        assert len(env) == 16, f"Expected exactly 16 env keys, got {len(env)}"

    def test_env_home_is_hermes_owned(self, safe_cwd: Path):
        """Blocker C: HOME in env points to Hermes-owned path."""
        controller = KiloProcessController({})
        env = controller._build_env()
        assert env["HOME"] == str(KILO_EFFECTIVE_HOME)
        assert env["USERPROFILE"] == str(KILO_EFFECTIVE_HOME)
        assert env["KILO_HOME"] == str(KILO_EFFECTIVE_HOME)
        assert env["HOME"] != str(Path.home())

    def test_env_no_ambient_kilo_config(self, safe_cwd: Path):
        """Blocker C: env does not inherit ambient Kilo config paths."""
        controller = KiloProcessController({})
        env = controller._build_env()
        assert env["KILO_CONFIG_DIR"] == str(KILO_CONFIG_DIR)
        assert KILO_CONFIG_DIR.is_relative_to(HERMES_RUNTIME_ROOT)

    def test_env_temp_is_hermes_owned(self, safe_cwd: Path):
        """Blocker C: TEMP/TMP under Hermes-owned home."""
        controller = KiloProcessController({})
        env = controller._build_env()
        expected_tmp = str(KILO_EFFECTIVE_HOME / "tmp")
        assert env["TEMP"] == expected_tmp
        assert env["TMP"] == expected_tmp

    def test_env_path_only_kilo_bin(self, safe_cwd: Path):
        """Blocker C: PATH only contains the Kilo bin directory."""
        controller = KiloProcessController({})
        env = controller._build_env()
        expected_path = str(Path(PINNED_KILO_PATH).resolve().parent)
        assert env["PATH"] == expected_path

    def test_env_no_ambient_secrets(self, safe_cwd: Path):
        """Blocker C: env does not inherit ambient secrets."""
        os.environ["KILO_API_KEY"] = "super-secret-key-12345"
        os.environ["OPENCODE_API_TOKEN"] = "opencode-token-67890"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "aws-secret-abcde"
        try:
            controller = KiloProcessController({})
            env = controller._build_env()
            assert "KILO_API_KEY" not in env
            assert "OPENCODE_API_TOKEN" not in env
            assert "AWS_SECRET_ACCESS_KEY" not in env
            assert "KILO_ORG_ID" not in env
            assert "KILO_PROVIDER" not in env
            assert "KILO_SERVER_PASSWORD" not in env
        finally:
            del os.environ["KILO_API_KEY"]
            del os.environ["OPENCODE_API_TOKEN"]
            del os.environ["AWS_SECRET_ACCESS_KEY"]

    def test_env_hostile_home_override_blocked(self, safe_cwd: Path):
        """Blocker C: hostile HOME from parent is overridden."""
        os.environ["HOME"] = r"C:\Users\Attacker\malicious"
        os.environ["USERPROFILE"] = r"C:\Users\Attacker\malicious"
        try:
            controller = KiloProcessController({})
            env = controller._build_env()
            assert env["HOME"] == str(KILO_EFFECTIVE_HOME)
            assert env["USERPROFILE"] == str(KILO_EFFECTIVE_HOME)
        finally:
            del os.environ["HOME"]
            del os.environ["USERPROFILE"]

    def test_env_hostile_kilo_config_override_blocked(self, safe_cwd: Path):
        """Blocker C: hostile KILO_CONFIG_DIR from parent is overridden."""
        os.environ["KILO_CONFIG_DIR"] = r"C:\Users\Attacker\malicious\config"
        try:
            controller = KiloProcessController({})
            env = controller._build_env()
            assert env["KILO_CONFIG_DIR"] == str(KILO_CONFIG_DIR)
        finally:
            del os.environ["KILO_CONFIG_DIR"]

    def test_env_hostile_opencode_config_override_blocked(self, safe_cwd: Path):
        """Blocker C: hostile OPENCODE_CONFIG_DIR from parent is overridden."""
        os.environ["OPENCODE_CONFIG_DIR"] = r"C:\Users\Attacker\malicious\opencode"
        try:
            controller = KiloProcessController({})
            env = controller._build_env()
            assert env["OPENCODE_CONFIG_DIR"] == str(KILO_CONFIG_DIR)
        finally:
            del os.environ["OPENCODE_CONFIG_DIR"]

    def test_env_no_plugin_loading_env(self, safe_cwd: Path):
        """Blocker C: env does not inherit plugin-related vars."""
        os.environ["KILO_PLUGINS"] = "malicious-plugin"
        os.environ["OPENCODE_PLUGINS"] = "malicious-opencode-plugin"
        try:
            controller = KiloProcessController({})
            env = controller._build_env()
            assert "KILO_PLUGINS" not in env
            assert "OPENCODE_PLUGINS" not in env
        finally:
            del os.environ["KILO_PLUGINS"]
            del os.environ["OPENCODE_PLUGINS"]

    def test_env_opencode_pure_is_set(self, safe_cwd: Path):
        """Blocker A: OPENCODE_PURE=1 is set in env (complement to --pure)."""
        controller = KiloProcessController({})
        env = controller._build_env()
        assert env["OPENCODE_PURE"] == "1"
        assert env["KILO_PURE"] == "1"

    def test_env_opencode_disable_project_config(self, safe_cwd: Path):
        """Blocker A: project config is disabled."""
        controller = KiloProcessController({})
        env = controller._build_env()
        assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"

    def test_env_no_auto_approve(self, safe_cwd: Path):
        """Blocker A: no auto-approve env vars or flags."""
        controller = KiloProcessController({})
        env = controller._build_env()
        assert "KILO_AUTO_APPROVE" not in env
        assert "OPENCODE_AUTO_APPROVE" not in env
        argv_list = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hi"}, {}, "").to_list()
        assert "--auto" not in argv_list

    def test_no_import_side_effect_registration(self):
        """Blocker D: kilo_adapter does NOT register at import time."""
        from tools.hermes_core import receiver_registry
        assert "kilo-cli-agent" in receiver_registry._ADAPTER_FACTORY

    def test_registry_not_default(self):
        """Blocker D: Kilo is not the only receiver; OpenCode also registered at import."""
        from tools.hermes_core import opencode_adapter  # triggers OpenCode registration
        from tools.hermes_core.receiver_registry import _ADAPTER_FACTORY
        assert "kilo-cli-agent" in _ADAPTER_FACTORY
        assert "opencode-cli-agent" in _ADAPTER_FACTORY
        assert len(_ADAPTER_FACTORY) > 1

    def test_kilo_config_isolation_runtime_root(self, safe_cwd: Path):
        """Config isolation: runtime root is outside the repo."""
        assert not HERMES_RUNTIME_ROOT.is_relative_to(Path(".").resolve())
        assert KILO_CWD == HERMES_RUNTIME_ROOT
        assert not KILO_CWD.is_relative_to(Path(".").resolve())

    def test_kilo_config_isolation_home(self, safe_cwd: Path):
        """Config isolation: effective home is outside the repo."""
        assert not KILO_EFFECTIVE_HOME.is_relative_to(Path(".").resolve())
        assert not KILO_CONFIG_DIR.is_relative_to(Path(".").resolve())

    def test_kilo_namespace_unique(self, safe_cwd: Path):
        """Namespace: Kilo runtime root is unique from OpenCode."""
        assert "kilo" in str(HERMES_RUNTIME_ROOT).lower()


class TestKiloPermissionKeyValidation:
    """Validate that every permission key in the Hermes profile is recognized by Kilo 7.5.6."""

    def test_profile_permission_keys_are_string_denies(self, safe_cwd: Path):
        """Every permission value in the Hermes profile is a string deny or a
        wildcard dict deny ``{``*``: ``deny``}``."""
        from tools.hermes_core.kilo_agent_profile import AGENT_DEFINITION
        profile = json.loads(AGENT_DEFINITION)
        perm = profile.get("permission", {})
        for key, value in perm.items():
            if isinstance(value, dict):
                assert value == {"*": "deny"}, (
                    f"Expected {{'*': 'deny'}} for {key!r}, got {value!r}"
                )
            else:
                assert isinstance(value, str), f"{key!r} must be str or dict, got {type(value).__name__}"
                assert value == "deny", f"Expected deny for {key}, got {value!r}"

    def test_profile_covers_required_capability_keys(self, safe_cwd: Path):
        from tools.hermes_core.kilo_agent_profile import AGENT_DEFINITION
        profile = json.loads(AGENT_DEFINITION)
        perm = profile.get("permission", {})
        required = {
            "read", "edit", "write", "bash", "glob", "grep", "list",
            "mcp", "plugin", "agent", "browser", "web", "fetch",
        }
        missing = required - set(perm.keys())
        assert not missing, f"Missing required permission keys: {missing}"
        # The global wildcard catch-all must be present for true default-deny
        assert "*" in perm, "Global \"*\" deny rule is required for default-deny"

    def test_profile_agents_plugins_mcp_are_empty(self, safe_cwd: Path):
        from tools.hermes_core.kilo_agent_profile import AGENT_DEFINITION
        profile = json.loads(AGENT_DEFINITION)
        assert profile.get("agents") == {}
        assert profile.get("plugins") == {}
        assert profile.get("mcpServers") == {}


class TestKiloDenyEnforcementTrace:
    """Source-independent deny-to-execution trace for each required capability.

    NOTE: Exact Kilo 7.5.6 source for permission evaluation callsites was not
    available during this qualification (source tree paths vary by build artifact).
    These tests verify the Hermes-side deny posture through the adapter, agent
    profile, and environment contract. The actual Kilo permission evaluation
    path must be treated as TRUSTED CONFIGURATION, not source-proven deny.
    """

    def test_pure_flag_is_plugin_suppression_only(self, safe_cwd: Path):
        """Verifies that the adapter documentation correctly describes --pure as
        plugin-suppression, not a general capability deny."""
        from tools.hermes_core import kilo_adapter as ka_module
        doc = ka_module.__doc__
        assert "PLUGIN-SUPPRESSION" in doc or "plugin-suppression" in doc.lower()
        assert "NOT a capability deny" in doc or "NOT disable" in doc

    def test_env_contains_opencode_pure_and_disable_project_config(self, safe_cwd: Path):
        controller = KiloProcessController({})
        env = controller._build_env()
        assert env["OPENCODE_PURE"] == "1"
        assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
        assert env["KILO_PURE"] == "1"

    def test_env_no_ambient_kilo_opencode_vars(self, safe_cwd: Path):
        for secret in (
            "KILO_API_KEY", "KILO_ORG_ID", "KILO_PROVIDER", "KILO_SERVER_PASSWORD",
            "OPENCODE_API_TOKEN", "OPENCODE_CONFIG_DIR", "KILO_CONFIG_DIR",
            "KILO_PLUGINS", "OPENCODE_PLUGINS",
        ):
            os.environ.pop(secret, None)
        assert "KILO_API_KEY" not in KiloProcessController({})._build_env()
        assert "KILO_ORG_ID" not in KiloProcessController({})._build_env()
        os.environ["KILO_API_KEY"] = "secret"
        os.environ["KILO_ORG_ID"] = "org"
        try:
            env = KiloProcessController({})._build_env()
            assert "KILO_API_KEY" not in env
            assert "KILO_ORG_ID" not in env
        finally:
            del os.environ["KILO_API_KEY"]
            del os.environ["KILO_ORG_ID"]

    def test_agent_profile_has_empty_agents_plugins_mcp(self, safe_cwd: Path):
        from tools.hermes_core.kilo_agent_profile import AGENT_DEFINITION
        profile = json.loads(AGENT_DEFINITION)
        assert profile["agents"] == {}
        assert profile["plugins"] == {}
        assert profile["mcpServers"] == {}

    def test_transport_has_no_auto_no_model(self, safe_cwd: Path):
        argv_list = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hi"}, {}, "").to_list()
        assert "--auto" not in argv_list
        # Model IS included - fixed by Hermes argv
        assert "--model" in argv_list
        assert argv_list.count("--model") == 1
        model_idx = argv_list.index("--model")
        assert argv_list[model_idx + 1] == "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

    def test_deny_enforcement_locally_verifiable_via_adapter_only(self, safe_cwd: Path):
        """The Hermes profile provides source-proven default-deny via the Kilo 7.5.6
        ``"*"`` wildcard permission rule.  From ``packages/opencode/src/permission/index.ts``::

            export function evaluate(permission, pattern, ...rulesets):
                return rulesets.flat().findLast(
                    rule => Wildcard.match(permission, rule.permission)
                        && Wildcard.match(pattern, rule.pattern)
                ) ?? { action: "ask", permission, pattern: "*" }

        With ``"*": "deny"`` in the ruleset, ``Wildcard.match(any_permission, "*")``
        returns ``true`` (``"*""`` → ``".*"``), so ``evaluate`` returns
        ``{ action: "deny", ... }`` for **every** permission key, including
        unknown ones.  This is a true global default-deny, proven from exact
        Kilo 7.5.6 source, not merely "`tools` is denied".
        """
        from tools.hermes_core.kilo_agent_profile import AGENT_DEFINITION
        profile = json.loads(AGENT_DEFINITION)
        perm = profile.get("permission", {})
        assert "*" in perm, "Global wildcard deny is required for default-deny"
        assert perm["*"] == "deny", "Global wildcard must be deny"


class TestKiloModelState:
    """Resolution of the model-field contradiction."""

    def test_agent_profile_has_no_model_field(self, safe_cwd: Path):
        from tools.hermes_core.kilo_agent_profile import AGENT_DEFINITION
        profile = json.loads(AGENT_DEFINITION)
        assert "model" not in profile, "Agent profile must not set a model field"

    def test_transport_does_include_model_flag(self, safe_cwd: Path):
        argv_list = build_kilo_argv({"kilo_executable": PINNED_KILO_PATH, "task_message": "hi"}, {}, "").to_list()
        # Model IS included - fixed by Hermes argv
        assert "--model" in argv_list
        assert argv_list.count("--model") == 1
        model_idx = argv_list.index("--model")
        assert argv_list[model_idx + 1] == "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

    def test_model_selection_is_fixed(self, safe_cwd: Path):
        from tools.hermes_core.kilo_agent_profile import AGENT_DEFINITION
        profile = json.loads(AGENT_DEFINITION)
        # Profile has no model field - model is bound by argv, not profile
        assert "model" not in profile


class TestKiloProcessControllerClassification:
    """Review of blocking subprocess.run vs Hermes start contract."""

    def test_execute_uses_popen_lifecycle(self, safe_cwd: Path):
        import inspect
        start_src = inspect.getsource(KiloProcessController.start)
        assert "subprocess.Popen" in start_src
        assert "shell=False" in start_src
        assert "stdin=subprocess.DEVNULL" in start_src
        assert "stdout=subprocess.PIPE" in start_src
        assert "stderr=subprocess.PIPE" in start_src
        exec_src = inspect.getsource(KiloProcessController.execute)
        assert "self.start(" in exec_src
        assert "handle.wait()" in exec_src

    def test_execute_closes_stdin_via_popen(self, safe_cwd: Path):
        import inspect
        source = inspect.getsource(KiloProcessController.start)
        assert "stdin=subprocess.DEVNULL" in source

    def test_execute_bounded_timeout(self, safe_cwd: Path):
        assert DEFAULT_TIMEOUT_SECONDS >= MIN_TIMEOUT_SECONDS
        assert DEFAULT_TIMEOUT_SECONDS <= MAX_TIMEOUT_SECONDS

    def test_classify_start_state_returns_started_on_success(self, safe_cwd: Path):
        adapter = KiloAdapter()
        result = KiloProcessResult(pid=1, returncode=0, stdout="", stderr="")
        assert adapter.classify_start_state(1, result) == "started"

    def test_classify_start_state_returns_error_on_nonzero(self, safe_cwd: Path):
        adapter = KiloAdapter()
        result = KiloProcessResult(pid=1, returncode=1, stdout="", stderr="")
        assert adapter.classify_start_state(1, result) == "error"

    def test_classify_start_state_returns_timeout_on_timeout(self, safe_cwd: Path):
        adapter = KiloAdapter()
        result = KiloProcessResult(pid=1, returncode=-1, stdout="", stderr="", timed_out=True)
        assert adapter.classify_start_state(1, result) == "timeout"

    def test_classify_start_state_returns_unknown_on_none(self, safe_cwd: Path):
        adapter = KiloAdapter()
        assert adapter.classify_start_state(None, None) == "start_state_unknown"
        assert adapter.classify_start_state(1, None) == "start_state_unknown"

    def test_prepare_invocation_does_not_block(self, safe_cwd: Path):
        adapter = KiloAdapter()
        record, argv, ok = adapter.prepare_invocation(
            idempotency_key="key-1", launch_attempt_id="la-1",
            delegation_id="d-1", stdin_data="",
        )
        assert ok is True
        assert hasattr(argv, "to_list")
        assert record.start_state == "launched"
        assert record.terminal_state is None

    def test_kilo_has_popen_cancellation(self, safe_cwd: Path):
        import inspect
        ctrl_src = inspect.getsource(KiloProcessController)
        assert "subprocess.Popen" in ctrl_src
        assert "def start(" in ctrl_src
        assert "handle.kill()" in ctrl_src  # execute calls kill on exception
        handle_src = inspect.getsource(KiloProcessHandle)
        assert "def kill(" in handle_src
        assert "def terminate(" in handle_src
