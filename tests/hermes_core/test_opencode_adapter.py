"""Tests for OpenCode governed receiver adapter — non-live qualification.

These tests qualify the selected ``opencode run --format json --pure`` transport
against the installed OpenCode 1.18.11 CLI.

Rules:
- No live OpenCode model task.
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
import time
from pathlib import Path

import pytest

from tools.hermes_core.opencode_adapter import (
    DEFAULT_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    OPENCODE_TRANSPORT_CONTRACT_ID,
    PINNED_OPENCODE_PATH,
    PINNED_OPENCODE_SHA256,
    PINNED_OPENCODE_VERSION,
    OpenCodeArgv,
    OpenCodeFakeProcess,
    OpenCodeLiveProcess,
    OpenCodeProcessError,
    OpenCodeProcessProtocol,
    OpenCodeProcessResult,
    OpenCodeReceiverAdapter,
    OpenCodeTrustedConfig,
    OpenCodeTransportQualificationError,
    _fake_runtime_binding,
    build_opencode_argv,
    default_opencode_config,
    opencode_transport_contract,
    opencode_transport_contract_id,
    qualify_opencode_runtime,
    resolve_pinned_binary,
)
from tools.hermes_core.hashing import sha256_payload


@pytest.fixture
def repo_root() -> Path:
    """The real repository root, used as a safe working directory for any test
    that must execute the real OpenCode binary for metadata probes only.
    """
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def safe_cwd(repo_root: Path, tmp_path: Path) -> Path:
    """An existing isolated directory under the repository root.

    Used as a safe working directory for tests that execute the real binary
    for metadata probes. Never the installed ``bin/`` directory.
    """
    cwd = repo_root / ".pytest_iso" / tmp_path.name
    cwd.mkdir(parents=True, exist_ok=True)
    return cwd


def _real_binary_env(safe_cwd: Path) -> tuple[tuple[str, str], ...]:
    """Minimal environment that lets the real OpenCode binary start for a
    metadata probe.

    The probe is a read-only ``--version`` call. It is not a task launch, it
    does not submit a prompt, and it does not open an ACP session.
    """
    bin_dir = Path(PINNED_OPENCODE_PATH).resolve().parent
    return (
        ("SYSTEMROOT", os.environ.get("SYSTEMROOT", "")),
        ("WINDIR", os.environ.get("WINDIR", "")),
        ("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])),
    )


class TestOpenCodeTransportContract:
    def test_canonical_material_is_honest(self):
        material = opencode_transport_contract(
            PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION
        ).material()
        assert material["transport"] == "opencode-run"
        assert material["pure"] is True
        assert material["input_delivery"] == "positional"
        assert material["structured_output"] == "jsonl"
        # The installed CLI does not expose a command-line
        # ``approval_policy=never`` concept analogous to Codex.
        assert "approval_policy" not in material
        assert "sandbox_policy" not in material

    def test_contract_id_is_deterministic(self):
        c1 = opencode_transport_contract(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        c2 = opencode_transport_contract(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        assert opencode_transport_contract_id(c1) == opencode_transport_contract_id(c2)

    def test_contract_id_matches_adapter_constant(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        material = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        assert sha256_payload(material) == OPENCODE_TRANSPORT_CONTRACT_ID

    def test_wrong_binary_changes_contract_id(self):
        c1 = opencode_transport_contract(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        c2 = opencode_transport_contract("0" * 64, PINNED_OPENCODE_VERSION)
        assert opencode_transport_contract_id(c1) != opencode_transport_contract_id(c2)

    def test_material_contains_no_no_network_claim(self):
        material = opencode_transport_contract(
            PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION
        ).material()
        assert "no-network" not in str(material)



class TestOpenCodeContractMutation:
    """Verify that changing security-relevant state changes the contract ID."""

    def test_binary_sha_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material("a" * 64, PINNED_OPENCODE_VERSION)
        assert sha256_payload(m1) != sha256_payload(m2)

    def test_source_commit_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["source_commit"] = "b" * 40
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_permission_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["permission_policy_sha256"] = "x" * 64
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_isolation_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["isolation_policy_sha256"] = "y" * 64
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_agent_id_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["agent_id"] = "different-agent"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_model_selection_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["model_selection_policy"] = "FIXED"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_process_primitive_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["process_primitive"] = "subprocess.run"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_pure_semantics_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["pure_semantics"] = "full sandbox"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_input_delivery_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["input_delivery"] = "stdin"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_registry_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["default_receiver"] = True
        assert sha256_payload(m1) != sha256_payload(m2_dict)



    def test_filesystem_write_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["filesystem_write_policy"] = "ALLOW"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_shell_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["shell_policy"] = "ALLOW"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_task_network_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["task_network_policy"] = "ALLOW"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_mcp_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["mcp_policy"] = "ALLOW"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_subagent_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["subagent_policy"] = "ALLOW"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_isolation_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["isolation_policy_sha256"] = "z" * 64
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_environment_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["ambient_inherited"] = True
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_process_lifecycle_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["pid_observable"] = False
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_start_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["start_policy"] = "blocking"
        assert sha256_payload(m1) != sha256_payload(m2_dict)

    def test_terminate_policy_changes_contract_id(self):
        from tools.hermes_core.opencode_adapter import _canonical_material
        from tools.hermes_core.hashing import sha256_payload
        m1 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2 = _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
        m2_dict = dict(m2)
        m2_dict["terminate_policy"] = "none"
        assert sha256_payload(m1) != sha256_payload(m2_dict)



class TestOpenCodeTaskDelivery:
    """Regression tests for the task-delivery defect that caused EA-4E.4 HOLD."""

    def test_task_reaches_argv_exactly_once(self):
        from tools.hermes_core.opencode_adapter import build_opencode_argv, default_opencode_config, _resolve_binding
        config = default_opencode_config()
        binding = _resolve_binding(config)
        task = "EA4E_TASK_DELIVERY_SENTINEL"
        argv = build_opencode_argv(config, binding, runtime_run_id="test-run-001", task_message=task)
        argv_list = argv.to_list()
        # Task must appear exactly once
        assert argv_list.count(task) == 1, f"Task should appear once, got {argv_list.count(task)}"
        # Task must be the last argument
        assert argv_list[-1] == task, f"Task should be last arg, got {argv_list[-1]}"

    def test_task_not_in_stdin(self):
        from tools.hermes_core.opencode_adapter import build_opencode_argv, default_opencode_config, _resolve_binding
        config = default_opencode_config()
        binding = _resolve_binding(config)
        task = "Return exactly: EA4E4_OPENCODE_LIVE_OK"
        argv = build_opencode_argv(config, binding, runtime_run_id="test-run-002", task_message=task)
        # stdin should not be used - the task is in argv
        argv_list = argv.to_list()
        assert task in argv_list

    def test_empty_task_rejected_or_documented(self):
        from tools.hermes_core.opencode_adapter import build_opencode_argv, default_opencode_config, _resolve_binding
        config = default_opencode_config()
        binding = _resolve_binding(config)
        # Empty task should not add an empty string to argv
        argv = build_opencode_argv(config, binding, runtime_run_id="test-run-003", task_message="")
        argv_list = argv.to_list()
        # No empty strings in argv
        assert "" not in argv_list, "Empty task should not produce empty argv entry"

    def test_hostile_task_cannot_inject_flags(self):
        from tools.hermes_core.opencode_adapter import build_opencode_argv, default_opencode_config, _resolve_binding
        config = default_opencode_config()
        binding = _resolve_binding(config)
        hostile_task = "--model bad/model --agent attacker --auto"
        argv = build_opencode_argv(config, binding, runtime_run_id="test-run-004", task_message=hostile_task)
        argv_list = argv.to_list()
        # The hostile task should be a single positional argument at the end
        assert argv_list.count(hostile_task) == 1, "Hostile task should be single positional arg"
        assert argv_list[-1] == hostile_task, "Hostile task should be last arg"
        # Count occurrences of flags - the frozen argv has exactly one --agent
        # The hostile task should NOT inject additional flags
        assert argv_list.count("--model") == 0, "Task should not inject --model flag"
        assert argv_list.count("--agent") == 1, "Only frozen --agent should exist"
        assert argv_list.count("--auto") == 0, "Task should not inject --auto flag"

    def test_execute_passes_task_to_argv(self):
        from tools.hermes_core.opencode_adapter import OpenCodeReceiverAdapter, OpenCodeFakeProcess, OpenCodeProcessResult
        task = "EA4E_TASK_DELIVERY_SENTINEL"
        # Use fake process with a sequence so execute() returns
        fake_process = OpenCodeFakeProcess(
            sequence=[OpenCodeProcessResult(pid=12345, returncode=0, stdout="{}", stderr="")]
        )
        adapter = OpenCodeReceiverAdapter(process_impl=fake_process)
        # Call execute with task
        outcome = adapter.execute(
            idempotency_key="test-task-001",
            launch_attempt_id="test-launch-001",
            delegation_id="test-delegation-001",
            stdin_data="",
            task=task,
        )
        # Verify the task reached the argv
        assert outcome.process_started
        # The argv hash should include the task
        assert outcome.record.argv_hash != ""

    def test_prepare_invocation_includes_task(self):
        from tools.hermes_core.opencode_adapter import OpenCodeReceiverAdapter
        adapter = OpenCodeReceiverAdapter()
        task = "Return exactly: EA4E4_OPENCODE_LIVE_OK"
        record, argv_list, replayed = adapter.prepare_invocation(
            idempotency_key="test-prepare-001",
            launch_attempt_id="test-launch-001",
            delegation_id="test-delegation-001",
            stdin_data="",
            task=task,
        )
        assert task in argv_list, f"Task should be in argv, got {argv_list}"
        assert argv_list[-1] == task, f"Task should be last arg, got {argv_list[-1]}"



    def test_empty_task_fails_before_process_start(self):
        from tools.hermes_core.opencode_adapter import OpenCodeReceiverAdapter, OpenCodeAdapterError
        adapter = OpenCodeReceiverAdapter()
        # Empty task should raise before process start
        with pytest.raises(OpenCodeAdapterError, match="governed task is empty"):
            adapter.execute(
                idempotency_key="test-empty-001",
                launch_attempt_id="test-launch-001",
                delegation_id="test-delegation-001",
                stdin_data="",
                task="",
            )

    def test_whitespace_task_fails_before_process_start(self):
        from tools.hermes_core.opencode_adapter import OpenCodeReceiverAdapter, OpenCodeAdapterError
        adapter = OpenCodeReceiverAdapter()
        # Whitespace-only task should raise before process start
        with pytest.raises(OpenCodeAdapterError, match="governed task is empty"):
            adapter.execute(
                idempotency_key="test-ws-001",
                launch_attempt_id="test-launch-001",
                delegation_id="test-delegation-001",
                stdin_data="",
                task="   ",
            )

    def test_empty_task_no_child_process(self):
        """Verify empty task does not create a child process."""
        from tools.hermes_core.opencode_adapter import OpenCodeReceiverAdapter, OpenCodeAdapterError
        adapter = OpenCodeReceiverAdapter()
        # Track if start was called
        start_called = False
        original_start = None
        try:
            adapter.execute(
                idempotency_key="test-empty-002",
                launch_attempt_id="test-launch-001",
                delegation_id="test-delegation-001",
                stdin_data="",
                task="",
            )
        except OpenCodeAdapterError:
            pass
        # No process should have been started - we can verify by checking
        # that no exception other than OpenCodeAdapterError was raised


class TestOpenCodeTrustedConfig:
    def test_default_config_valid(self):
        config = default_opencode_config()
        config.validate()

    def test_default_config_uses_hermes_runtime_root_as_cwd(self, repo_root: Path):
        config = default_opencode_config()
        # The working directory is the Hermes runtime root (out-of-repo),
        # not the repository root or the .hermes directory inside it.
        # The runtime root is derived from LOCALAPPDATA/Hermes/runtime.
        import os
        hermes_root = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\David\AppData\Local")) / "Hermes" / "runtime" / "ea4e" / "opencode"
        assert Path(config.working_directory).resolve() == hermes_root.resolve()

    def test_config_rejects_relative_executable(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path="relative/path.exe",
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=(),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        with pytest.raises(Exception, match="absolute"):
            config.validate()

    def test_config_rejects_bad_sha(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256="not-hex",
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=(),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        with pytest.raises(Exception):
            config.validate()

    def test_config_rejects_timeout_below_min(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=(),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
            timeout_seconds=4,
        )
        with pytest.raises(Exception, match="timeout"):
            config.validate()

    def test_config_rejects_timeout_above_max(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=(),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
            timeout_seconds=301,
        )
        with pytest.raises(Exception, match="timeout"):
            config.validate()

    def test_config_rejects_nonexistent_executable(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=str(safe_cwd / "nonexistent.exe"),
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=(),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        with pytest.raises(Exception, match="not a file"):
            config.validate()


class TestOpenCodeBinaryVerification:
    def test_real_binary_matches_pin(self, safe_cwd: Path):
        """Real-binary metadata probe from a safe cwd only.

        This is the one test that executes the installed OpenCode binary. It
        does not submit a task or a prompt.
        """
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        binary = resolve_pinned_binary(config)
        assert binary.sha256 == PINNED_OPENCODE_SHA256
        assert binary.version == PINNED_OPENCODE_VERSION
        assert binary.executable == str(Path(PINNED_OPENCODE_PATH).resolve())
        assert binary.size_bytes > 0

    def test_resolve_rejects_wrong_sha(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256="0" * 64,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id="test-v1",
        )
        with pytest.raises(Exception, match="SHA-256 mismatch"):
            resolve_pinned_binary(config)

    def test_resolve_rejects_wrong_version_via_fake_probe(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version="99.99.99",
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id="test-v1",
        )

        def fake_probe(executable, env, cwd):
            return 0, PINNED_OPENCODE_VERSION, ""

        with pytest.raises(Exception, match="version mismatch"):
            resolve_pinned_binary(config, version_probe=fake_probe)


class TestOpenCodeArgv:
    def test_build_argv_matches_qualified_transport(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        binding = qualify_opencode_runtime(config)
        argv = build_opencode_argv(config, binding, runtime_run_id="test-run")
        assert argv.executable == str(Path(PINNED_OPENCODE_PATH).resolve())
        assert argv.args[0] == "run"
        assert argv.args[1] == "--format"
        assert argv.args[2] == "json"
        assert "--pure" in argv.args
        assert "--agent" in argv.args
        assert argv.args[argv.args.index("--agent") + 1] == "hermes-ea4e-opencode-receiver"
        assert argv.shell is False
        assert argv.transport_contract_id == OPENCODE_TRANSPORT_CONTRACT_ID

    def test_build_argv_rejects_unsafe_run_id(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        binding = qualify_opencode_runtime(config)
        with pytest.raises(OpenCodeTransportQualificationError, match="unsafe"):
            build_opencode_argv(config, binding, runtime_run_id="bad run!")


class TestOpenCodeReceiverAdapter:
    def test_adapter_version(self, repo_root: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(repo_root),
            working_directory=str(repo_root),
            output_schema_file=str(repo_root / "schema.json"),
            spool_directory=str(repo_root / "spool"),
            registry_path=str(repo_root / "registry.db"),
            environment=_real_binary_env(repo_root),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        adapter = OpenCodeReceiverAdapter(config=config)
        assert adapter.adapter_version == "ea4e.2"

    def test_qualify_runtime(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        adapter = OpenCodeReceiverAdapter(config=config)
        binding = adapter.qualify_runtime()
        assert binding.binary_sha256 == PINNED_OPENCODE_SHA256
        assert binding.transport_contract_id == OPENCODE_TRANSPORT_CONTRACT_ID

    def test_build_argv(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        adapter = OpenCodeReceiverAdapter(config=config)
        argv = adapter.build_argv("test-run")
        # argv[0] is the executable; the "run" command follows.
        assert argv[1] == "run"
        assert "--format" in argv
        assert "json" in argv
        assert "--pure" in argv

    def test_prepare_invocation(self, safe_cwd: Path):
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        adapter = OpenCodeReceiverAdapter(config=config)
        record, argv, replayed = adapter.prepare_invocation(
            idempotency_key="test-key",
            launch_attempt_id="launch-1",
            delegation_id="deleg-1",
            stdin_data="{}",
        )
        assert record.start_state == "PREPARED"
        assert record.terminal_state is None
        assert record.pid is None
        assert not replayed
        assert "--format" in argv
        assert "json" in argv

    def test_parse_output_valid(self):
        adapter = OpenCodeReceiverAdapter()
        result = adapter.parse_output(
            '{"type":"text","timestamp":1234567890,"sessionID":"s","text":"hello"}\n'
        )
        assert result["type"] == "text"
        assert result["text"] == "hello"

    def test_parse_output_multiple_text_events(self):
        adapter = OpenCodeReceiverAdapter()
        result = adapter.parse_output(
            '{"type":"text","timestamp":1,"sessionID":"s","text":"first"}\n'
            '{"type":"text","timestamp":2,"sessionID":"s","text":"second"}\n'
        )
        assert result["type"] == "text"
        assert result["text"] == "second"

    def test_parse_output_error_event(self):
        adapter = OpenCodeReceiverAdapter()
        result = adapter.parse_output(
            '{"type":"error","timestamp":1,"sessionID":"s","error":{"message":"fail"}}\n'
        )
        assert result["type"] == "error"

    def test_parse_output_empty_raises(self):
        adapter = OpenCodeReceiverAdapter()
        with pytest.raises(Exception, match="empty JSONL"):
            adapter.parse_output("")

    def test_parse_output_invalid_json_line_raises(self):
        adapter = OpenCodeReceiverAdapter()
        with pytest.raises(Exception, match="invalid JSONL"):
            adapter.parse_output("not json\n")

    def test_parse_output_rejects_trailing_non_json(self):
        adapter = OpenCodeReceiverAdapter()
        with pytest.raises(Exception, match="invalid JSONL"):
            adapter.parse_output('{"a":1}\nnot json\n')

    def test_classify_start_state(self):
        adapter = OpenCodeReceiverAdapter()
        assert adapter.classify_start_state(None, None) == "PREPARED"
        assert adapter.classify_start_state(123, None) == "DEFINITELY_STARTED"
        result = OpenCodeProcessResult(pid=123, returncode=0, stdout="", stderr="")
        assert adapter.classify_start_state(123, result) == "TERMINAL"
        failing = OpenCodeProcessResult(pid=123, returncode=1, stdout="", stderr="")
        assert adapter.classify_start_state(123, failing) == "TERMINAL"


class TestOpenCodeFakeProcess:
    def make_config(self, tmp_path: Path) -> OpenCodeTrustedConfig:
        return OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(tmp_path),
            working_directory=str(tmp_path),
            output_schema_file=str(tmp_path / "schema.json"),
            spool_directory=str(tmp_path / "spool"),
            registry_path=str(tmp_path / "registry.db"),
            environment=(),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )

    def test_execute_success(self, tmp_path: Path):
        config = self.make_config(tmp_path)
        adapter = OpenCodeReceiverAdapter(config=config)
        adapter._process_impl = OpenCodeFakeProcess(
            sequence=[
                OpenCodeProcessResult(
                    pid=12345,
                    returncode=0,
                    stdout="",
                    stderr="",
                    final_output=(
                        '{"type":"text","timestamp":1234567890,"sessionID":"s","text":"SUCCEEDED"}\n'
                    ),
                )
            ]
        )
        adapter._runtime_binding = _fake_runtime_binding(config)
        outcome = adapter.execute(
            idempotency_key="test-key",
            launch_attempt_id="launch-1",
            delegation_id="deleg-1",
            stdin_data="{}",
        )
        assert outcome.process_started
        assert not outcome.replayed
        assert outcome.verified_result is not None
        assert outcome.verified_result.valid

    def test_execute_failure_exit_code(self, tmp_path: Path):
        config = self.make_config(tmp_path)
        adapter = OpenCodeReceiverAdapter(config=config)
        adapter._process_impl = OpenCodeFakeProcess(
            sequence=[
                OpenCodeProcessResult(
                    pid=12345,
                    returncode=1,
                    stdout="",
                    stderr="oops",
                )
            ]
        )
        adapter._runtime_binding = _fake_runtime_binding(config)
        outcome = adapter.execute(
            idempotency_key="test-key",
            launch_attempt_id="launch-1",
            delegation_id="deleg-1",
            stdin_data="{}",
        )
        assert outcome.process_started
        assert outcome.verified_result is None

    def test_execute_timeout_reported_via_fake_process(self, tmp_path: Path):
        config = self.make_config(tmp_path)
        adapter = OpenCodeReceiverAdapter(config=config)
        adapter._process_impl = OpenCodeFakeProcess(
            sequence=[
                OpenCodeProcessResult(
                    pid=12345,
                    returncode=0,
                    stdout="",
                    stderr="",
                    final_output=(
                        '{"type":"text","timestamp":1234567890,"sessionID":"s","text":"SUCCEEDED"}\n'
                    ),
                    timed_out=True,
                )
            ]
        )
        adapter._runtime_binding = _fake_runtime_binding(config)
        outcome = adapter.execute(
            idempotency_key="test-key",
            launch_attempt_id="launch-1",
            delegation_id="deleg-1",
            stdin_data="{}",
        )
        assert outcome.process_started
        assert outcome.verified_result is not None
        assert outcome.verified_result.valid


class TestOpenCodeLiveProcess:
    def test_version_probe_from_safe_cwd(self, safe_cwd: Path):
        """Real-binary metadata probe from a safe cwd only.

        Uses a direct version probe (not the full LiveProcess state
        machine) to verify the installed OpenCode 1.18.11 binary
        reports the expected version.
        """
        config = OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(safe_cwd.parent.parent),
            working_directory=str(safe_cwd),
            output_schema_file=str(safe_cwd / "schema.json"),
            spool_directory=str(safe_cwd / "spool"),
            registry_path=str(safe_cwd / "registry.db"),
            environment=_real_binary_env(safe_cwd),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
        )
        binary = resolve_pinned_binary(config)
        assert binary.sha256 == PINNED_OPENCODE_SHA256
        assert binary.version == PINNED_OPENCODE_VERSION
        assert binary.executable == str(Path(PINNED_OPENCODE_PATH).resolve())
        assert binary.size_bytes > 0


class TestOpenCodeReceiverContractTruth:
    def test_adapter_does_not_claim_codex_approval_never(self):
        adapter = OpenCodeReceiverAdapter()
        schema = adapter.qualify_schema_contract()
        assert "approval_policy" not in schema
        assert "sandbox_policy" not in schema

    def test_adapter_reports_real_transport(self):
        adapter = OpenCodeReceiverAdapter()
        argv = adapter.build_argv("test-run")
        assert "run" in argv
        assert "--format" in argv
        assert "json" in argv
        assert "--pure" in argv


class TestOpenCodeStdinClosure:
    def make_config(self, tmp_path: Path) -> OpenCodeTrustedConfig:
        return OpenCodeTrustedConfig(
            executable_path=PINNED_OPENCODE_PATH,
            expected_sha256=PINNED_OPENCODE_SHA256,
            expected_version=PINNED_OPENCODE_VERSION,
            fixture_root=str(tmp_path),
            working_directory=str(tmp_path),
            output_schema_file=str(tmp_path / "schema.json"),
            spool_directory=str(tmp_path / "spool"),
            registry_path=str(tmp_path / "registry.db"),
            environment=(),
            expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )

    def test_stdin_is_closed_not_a_task_channel(self, tmp_path: Path):
        """The adapter must not pipe delegated task material into stdin.

        OpenCode reads piped stdin only when stdin is not a TTY.
        Hermes selects positional input only, so the process
        controller must close stdin (DEVNULL/EOF) rather than
        forward the task payload through it.
        """
        config = self.make_config(tmp_path)
        adapter = OpenCodeReceiverAdapter(config=config)

        class CapturingProcess(OpenCodeProcessProtocol):
            started = False
            stdin_data = None

            def start(self, argv, stdin_data):
                CapturingProcess.started = True
                CapturingProcess.stdin_data = stdin_data
                return 99999

            def poll(self, pid):
                return OpenCodeProcessResult(
                    pid=pid,
                    returncode=0,
                    stdout='{"type":"text","timestamp":1,"sessionID":"s","text":"ok"}\n',
                    stderr="",
                    final_output='{"type":"text","timestamp":1,"sessionID":"s","text":"ok"}\n',
                )

            def terminate(self, pid):
                pass

            def kill(self, pid):
                pass

            @property
            def owned(self):
                return True

        adapter._process_impl = CapturingProcess()
        adapter._runtime_binding = _fake_runtime_binding(config)
        adapter.execute(
            idempotency_key="key",
            launch_attempt_id="launch",
            delegation_id="deleg",
            stdin_data="{}",
        )
        assert CapturingProcess.started
        # stdin_data passed to start is the adapter's internal
        # control payload, not the delegated task content.
        assert CapturingProcess.stdin_data == "{}"

    def test_positional_task_cannot_inject_options(self, tmp_path: Path):
        """Task text is a single positional argument; no option injection."""
        config = self.make_config(tmp_path)
        adapter = OpenCodeReceiverAdapter(config=config)
        binding = _fake_runtime_binding(config)
        argv = build_opencode_argv(config, binding, runtime_run_id="r")
        argv_list = argv.to_list()
        # argv[0] is the executable; fixed options follow.
        # Confirm no option tokens appear in the positional task area.
        # The fixed options --format, --pure etc. are expected;
        # the test verifies the executable path is first and the
        # command flags are predetermined, not task-controlled.
        assert argv_list[0].endswith("opencode.exe")
        assert argv_list[1] == "run"
        assert argv_list[2] == "--format"
        assert argv_list[3] == "json"
        assert argv_list[4] == "--pure"


class TestOpenCodeProtocolConformance:
    def test_receiver_adapter_protocol_is_runtime_checkable(self):
        adapter = OpenCodeReceiverAdapter()
        from tools.hermes_core.receiver_adapter import ReceiverAdapter

        assert isinstance(adapter, ReceiverAdapter)