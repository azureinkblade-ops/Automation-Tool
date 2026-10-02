"""OpenCode governed receiver adapter — non-live qualification.

Selected transport: `opencode run --format json --pure`

This uses the installed OpenCode 1.18.11 non-interactive structured-output
mode. It does NOT open a listener socket. It emits raw JSON events on stdout
for a requested task/session.

All task-level behavior in this qualification is fake. No live model.
No live OpenCode task.

Loopback ACP (`opencode acp --hostname 127.0.0.1 --port 0`) remains a
separate future capability. It is NOT activated or qualified here.

OpenCode-specific security/permission semantics are reported only where
inspectable from the installed CLI. This adapter does NOT claim Codex
semantics such as a universal `approval_policy=never` or any equivalent
`--no-network` flag unless the installed CLI independently provides them.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.receiver_adapter import (
    BinaryIdentity,
    BinaryVerificationError,
    ExecutionOutcome,
    InvocationRecord,
    ProcessResult,
    QualifiedRuntimeBinding,
    ReceiverCancelledError,
    ReceiverParseError,
    ReceiverProcessError,
    ReceiverReplayConflictError,
    ReceiverStartStateUnknownError,
    ReceiverTimeoutError,
    VerifiedResult,
)
from tools.hermes_core.receiver_registry import register_adapter

PINNED_OPENCODE_PATH = r"C:\Users\David\AppData\Local\hermes\node\node_modules\opencode-ai\bin\opencode.exe"
PINNED_OPENCODE_SHA256 = "578d7eb3fff2c807fc0dedaab5e5d9177713a9560fa4304db6a0161111e9cc35"
PINNED_OPENCODE_VERSION = "1.18.11"
PINNED_OPENCODE_ADAPTER_VERSION = "ea4e.2"
PINNED_OPENCODE_TRANSPORT = "opencode-run"

INPUT_DELIVERY = "positional"
STRUCTURED_OUTPUT = "jsonl"

MIN_TIMEOUT_SECONDS = 5
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 300

# Effective-home isolation policy: all OpenCode config discovery roots
# are redirected under a Hermes-owned runtime boundary OUTSIDE the
# Automation Tool repository and all git worktrees.
# Determined from os.environ["LOCALAPPDATA"] / "Hermes" / "runtime".
_HERMES_APP_DATA = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\David\AppData\Local"))
HERMES_RUNTIME_ROOT = _HERMES_APP_DATA / "Hermes" / "runtime" / "ea4e" / "opencode"
OPENCODE_EFFECTIVE_HOME = HERMES_RUNTIME_ROOT / "home"
OPENCODE_CONFIG_DIR = HERMES_RUNTIME_ROOT / "config"
OPENCODE_HOME_OPENCODE = OPENCODE_EFFECTIVE_HOME / ".opencode"
# The out-of-repo cwd is the Hermes runtime root; no .opencode/ exists there.
OPENCODE_CWD = HERMES_RUNTIME_ROOT
OPENCODE_AGENT_ID = "hermes-ea4e-opencode-receiver"


def _permission_policy_material() -> dict[str, Any]:
    """Canonical permission policy material for the OpenCode transport contract."""
    config_path = OPENCODE_HOME_OPENCODE / "config.json"
    if config_path.exists():
        import json as _json
        return _json.loads(config_path.read_text(encoding="utf-8"))
    return {"agent": {OPENCODE_AGENT_ID: {"permission": {"*": "deny", "read": "allow", "edit": "deny", "write": "deny", "bash": "deny", "mcp": "deny", "browser": "deny", "task": "deny"}}}}


def _isolation_policy_material() -> dict[str, Any]:
    """Canonical isolation policy material for the OpenCode transport contract.
    
    Builds the environment policy from the actual qualified implementation.
    """
    runtime = HERMES_RUNTIME_ROOT
    bin_dir = Path(PINNED_OPENCODE_PATH).resolve().parent
    env_names = (
        "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    )
    env = []
    for name in env_names:
        if name in os.environ:
            env.append((name, os.environ[name]))
    env.append(("OPENCODE_TEST_HOME", str(OPENCODE_EFFECTIVE_HOME)))
    env.append(("HOME", str(OPENCODE_EFFECTIVE_HOME)))
    env.append(("USERPROFILE", str(OPENCODE_EFFECTIVE_HOME)))
    env.append(("OPENCODE_CONFIG_DIR", str(OPENCODE_CONFIG_DIR)))
    env.append(("OPENCODE_DISABLE_PROJECT_CONFIG", "1"))
    env.append(("OPENCODE_PURE", "1"))
    env.append(("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])))
    
    env_keys = sorted([k for k, v in env])
    
    return {
        "runtime_root": str(runtime),
        "cwd": str(OPENCODE_CWD),
        "effective_home": str(OPENCODE_EFFECTIVE_HOME),
        "config_root": str(OPENCODE_CONFIG_DIR),
        "runtime_root_within_repo": False,
        "cwd_within_repo": False,
        "ambient_inherited": False,
        "config_isolation": "HOME, OPENCODE_CONFIG_DIR redirected to Hermes-controlled runtime root",
        "environment_keys": env_keys,
        "project_config_disabled": True,
        "pure_env_set": True,
        "stdin_policy": "subprocess.DEVNULL",
        "stdin_bytes_written": 0,
    }


def _canonical_material(
    binary_sha256: str,
    binary_version: str,
    *,
    transport: str = PINNED_OPENCODE_TRANSPORT,
    pure: bool = True,
    input_delivery: str = INPUT_DELIVERY,
    structured_output: str = STRUCTURED_OUTPUT,
    stdout_capture: str = "PIPE",
    stderr_capture: str = "PIPE",
    stream_drain_policy: str = "concurrent-threads",
    spool_owner: str = "HERMES",
) -> dict[str, Any]:
    """Canonical material describing the qualified OpenCode transport/interface."""
    permission_material = _permission_policy_material()
    isolation_material = _isolation_policy_material()

    return {
        # Binary identity
        "adapter_version": PINNED_OPENCODE_ADAPTER_VERSION,
        "binary_path": PINNED_OPENCODE_PATH,
        "binary_sha256": binary_sha256,
        "binary_version": binary_version,

        # Source
        "source_repository": "https://github.com/anomalyco/opencode",
        "source_tag": "v1.18.11",
        "source_commit": "012c2f57f976489d88bd4598a056b4bdcdd428ee",

        # Transport interface
        "input_delivery": input_delivery,
        "pure": pure,
        "pure_semantics": "plugin-suppression only",
        "structured_output": structured_output,
        "stdout_capture": stdout_capture,
        "stderr_capture": stderr_capture,
        "stream_drain_policy": stream_drain_policy,
        "spool_owner": spool_owner,
        "stdout_retention_limit": 1048576,
        "stderr_retention_limit": 131072,
        "overflow_policy": "RETAIN_BOUNDED_DRAIN_REMAINDER",
        "stdin_policy": "DEVNULL_ZERO_BYTES",
        "reader_error_policy": "FAIL_CAPTURE",
        "reader_join_policy": "JOIN_WITH_TIMEOUT_5S",
        "reader_finalization_policy": "REQUIRE_DEAD_BEFORE_RESULT",
        "parser_schema": "OPENCODE_JSONL_NESTED_PART_TEXT",
        "transport": transport,

        # Fixed argv policy
        "fixed_argv_policy": [
            "<opencode_executable>", "run", "--format", "json", "--pure",
            "--agent", OPENCODE_AGENT_ID, "<task_message>",
        ],
        "fixed_argv_note": "positional task input; no task-controlled flags",

        # Receiver/agent
        "agent_id": OPENCODE_AGENT_ID,
        "receiver_id": "opencode-cli-agent",

        # Model policy
        "model_selection_policy": "LIVE-GATE DEFERRED",
        "profile_model_field": "ABSENT",

        # Permission policy (hash-bound)
        "global_default_deny": True,
        "permission_policy_sha256": sha256_payload(permission_material),
        "unknown_tool_policy": "DENY",

        # Explicit capability bindings (hash-bound)
        "filesystem_write_policy": "DENY",
        "shell_policy": "DENY",
        "task_network_policy": "DENY",
        "mcp_policy": "DENY",
        "subagent_policy": "DENY",

        # Isolation policy (hash-bound)
        "ambient_inherited": False,
        "config_isolation": "HOME, OPENCODE_CONFIG_DIR redirected to Hermes-controlled runtime root",
        "config_root": str(OPENCODE_CONFIG_DIR),
        "cwd": str(OPENCODE_CWD),
        "cwd_within_repo": False,
        "effective_home": str(OPENCODE_EFFECTIVE_HOME),
        "isolation_policy_sha256": sha256_payload(isolation_material),
        "runtime_root": str(HERMES_RUNTIME_ROOT),
        "runtime_root_within_repo": False,

        # Process lifecycle
        "process_primitive": "subprocess.Popen",
        "shell": False,
        "start_policy": "Popen with DEVNULL stdin, PIPE stdout/stderr",
        "pid_observable": True,
        "poll_policy": "process.poll() returns Optional[int]",
        "terminate_policy": "process.terminate()",
        "kill_policy": "process.kill()",
        "stdin_policy": "subprocess.DEVNULL",
        "stdin_bytes_written": 0,
        "timeout_default": DEFAULT_TIMEOUT_SECONDS,
        "timeout_max": MAX_TIMEOUT_SECONDS,
        "timeout_min": MIN_TIMEOUT_SECONDS,

        # Registry policy
        "default_receiver": False,
        "failover": "OFF",
        "production_routing": "OFF",
        "registry_policy": "explicit static initialization via register_adapter()",

        # Task delivery
        "task_delivery_path": "execute(task) -> prepare_invocation(task) -> build_argv(task_message) -> positional argv",
        "empty_task_policy": "FAIL_BEFORE_PROCESS_START",
        "whitespace_task_policy": "FAIL_BEFORE_PROCESS_START",
    }


OPENCODE_TRANSPORT_CONTRACT_ID = sha256_payload(
    _canonical_material(PINNED_OPENCODE_SHA256, PINNED_OPENCODE_VERSION)
)


class OpenCodeAdapterError(RuntimeError):
    pass


class OpenCodeBinaryVerificationError(OpenCodeAdapterError, BinaryVerificationError):
    pass


class OpenCodeTransportQualificationError(OpenCodeAdapterError):
    pass


class OpenCodeProcessError(OpenCodeAdapterError, ReceiverProcessError):
    pass


class OpenCodeTimeoutError(OpenCodeAdapterError, ReceiverTimeoutError):
    pass


class OpenCodeCancelledError(OpenCodeAdapterError, ReceiverCancelledError):
    pass


class OpenCodeParseError(OpenCodeAdapterError, ReceiverParseError):
    pass


class OpenCodeStartStateUnknownError(OpenCodeAdapterError, ReceiverStartStateUnknownError):
    pass


class OpenCodeReplayConflictError(OpenCodeAdapterError, ReceiverReplayConflictError):
    pass


@dataclass(frozen=True)
class OpenCodeTrustedConfig:
    executable_path: str
    expected_sha256: str
    expected_version: str
    fixture_root: str
    working_directory: str
    output_schema_file: str
    spool_directory: str
    registry_path: str
    environment: tuple[tuple[str, str], ...]
    expected_transport_contract_id: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def validate(self) -> None:
        if not Path(self.executable_path).is_absolute():
            raise OpenCodeBinaryVerificationError("executable path must be absolute")
        if len(self.expected_sha256) != 64:
            raise OpenCodeBinaryVerificationError("SHA-256 must have 64 characters")
        try:
            int(self.expected_sha256, 16)
        except ValueError:
            raise OpenCodeBinaryVerificationError("SHA-256 is not hexadecimal")
        if not (MIN_TIMEOUT_SECONDS <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS):
            raise OpenCodeTimeoutError("timeout out of range")
        _executable = Path(self.executable_path).resolve()
        if not _executable.is_file():
            raise OpenCodeBinaryVerificationError("pinned path is not a file")


def default_opencode_config() -> OpenCodeTrustedConfig:
    """Default trusted OpenCode configuration.

    The working directory is the Hermes runtime root (out-of-repo),
    not the repository root or the installed OpenCode package directory.
    The effective home is redirected to a Hermes-owned path so that
    OpenCode's separately loaded .opencode/ resolves inside the
    trusted boundary instead of the user's ordinary home.
    """
    runtime = HERMES_RUNTIME_ROOT
    bin_dir = Path(PINNED_OPENCODE_PATH).resolve().parent
    # Effective-home isolation: redirect os.homedir() and Global.Path.home
    # to the Hermes-owned effective home. Also set OPENCODE_CONFIG_DIR to
    # isolate the global config root. Disable project config loading.
    env_names = (
        "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    )
    env = []
    for name in env_names:
        if name in os.environ:
            env.append((name, os.environ[name]))
    # Bind the effective-home isolation variables explicitly.
    # These override any ambient values and redirect all config roots.
    # Each name appears exactly once in the final environment tuple.
    env.append(("OPENCODE_TEST_HOME", str(OPENCODE_EFFECTIVE_HOME)))
    env.append(("HOME", str(OPENCODE_EFFECTIVE_HOME)))
    env.append(("USERPROFILE", str(OPENCODE_EFFECTIVE_HOME)))
    env.append(("OPENCODE_CONFIG_DIR", str(OPENCODE_CONFIG_DIR)))
    env.append(("OPENCODE_DISABLE_PROJECT_CONFIG", "1"))
    env.append(("OPENCODE_PURE", "1"))
    env.append(("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])))
    return OpenCodeTrustedConfig(
        executable_path=PINNED_OPENCODE_PATH,
        expected_sha256=PINNED_OPENCODE_SHA256,
        expected_version=PINNED_OPENCODE_VERSION,
        fixture_root=str(HERMES_RUNTIME_ROOT),
        working_directory=str(HERMES_RUNTIME_ROOT),
        output_schema_file=str(runtime / "hermes-result-v1.schema.json"),
        spool_directory=str(runtime / "spool"),
        registry_path=str(runtime / "transport.sqlite3"),
        environment=tuple(sorted(env)),
        expected_transport_contract_id=OPENCODE_TRANSPORT_CONTRACT_ID,
    )


@dataclass(frozen=True)
class OpenCodeTransportContract:
    adapter_version: str
    binary_sha256: str
    binary_version: str
    transport: str
    pure: bool
    input_delivery: str
    structured_output: str
    permission_policy_sha256: str = ""
    isolation_policy_sha256: str = ""
    stdout_capture: str = "PIPE"
    stderr_capture: str = "PIPE"
    stream_drain_policy: str = "concurrent-threads"
    spool_owner: str = "HERMES"

    def material(self) -> dict[str, Any]:
        return _canonical_material(
            self.binary_sha256,
            self.binary_version,
            transport=self.transport,
            pure=self.pure,
            input_delivery=self.input_delivery,
            structured_output=self.structured_output,
            stdout_capture=self.stdout_capture,
            stderr_capture=self.stderr_capture,
            stream_drain_policy=self.stream_drain_policy,
            spool_owner=self.spool_owner,
        )


def opencode_transport_contract(
    binary_sha256: str,
    binary_version: str,
    *,
    transport: str = PINNED_OPENCODE_TRANSPORT,
    pure: bool = True,
    input_delivery: str = INPUT_DELIVERY,
    structured_output: str = STRUCTURED_OUTPUT,
    stdout_capture: str = "PIPE",
    stderr_capture: str = "PIPE",
    stream_drain_policy: str = "concurrent-threads",
    spool_owner: str = "HERMES",
) -> OpenCodeTransportContract:
    permission_material = _permission_policy_material()
    isolation_material = _isolation_policy_material()
    return OpenCodeTransportContract(
        adapter_version=PINNED_OPENCODE_ADAPTER_VERSION,
        binary_sha256=binary_sha256,
        binary_version=binary_version,
        transport=transport,
        pure=pure,
        input_delivery=input_delivery,
        structured_output=structured_output,
        permission_policy_sha256=sha256_payload(permission_material),
        isolation_policy_sha256=sha256_payload(isolation_material),
        stdout_capture=stdout_capture,
        stderr_capture=stderr_capture,
        stream_drain_policy=stream_drain_policy,
        spool_owner=spool_owner,
    )


def opencode_transport_contract_id(contract: OpenCodeTransportContract) -> str:
    return sha256_payload(contract.material())


VersionProbe = Callable[[str, tuple[tuple[str, str], ...], str], tuple[int, str, str]]


def _version_probe(executable: str, env: tuple[tuple[str, str], ...], cwd: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [executable, "--version"],
        cwd=Path(cwd).resolve(),
        env=dict(env),
        shell=False,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def resolve_pinned_binary(
    config: Optional[OpenCodeTrustedConfig] = None,
    *,
    version_probe: Optional[VersionProbe] = None,
) -> BinaryIdentity:
    trusted = config or default_opencode_config()
    trusted.validate()
    executable = Path(trusted.executable_path).resolve(strict=True)
    if not executable.is_file():
        raise OpenCodeBinaryVerificationError("pinned path is not a file")
    digest = hashlib.sha256()
    with executable.open("rb") as h:
        for chunk in iter(lambda: h.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != trusted.expected_sha256:
        raise OpenCodeBinaryVerificationError(
            f"SHA-256 mismatch: expected {trusted.expected_sha256}, got {actual}"
        )
    probe = version_probe or _version_probe
    code, stdout, stderr = probe(
        str(executable), trusted.environment, trusted.working_directory
    )
    if code != 0:
        raise OpenCodeBinaryVerificationError(f"version probe exited {code}: {stderr[:256]}")
    if stdout != trusted.expected_version:
        raise OpenCodeBinaryVerificationError(
            f"version mismatch: expected {trusted.expected_version!r}, got {stdout!r}"
        )
    return BinaryIdentity(actual, stdout, str(executable), executable.stat().st_size)


def qualify_opencode_runtime(
    config: OpenCodeTrustedConfig,
    *,
    version_probe: Optional[VersionProbe] = None,
) -> QualifiedRuntimeBinding:
    binary = resolve_pinned_binary(config, version_probe=version_probe)
    contract = opencode_transport_contract(binary.sha256, binary.version)
    contract_id = opencode_transport_contract_id(contract)
    if contract_id != config.expected_transport_contract_id:
        raise OpenCodeTransportQualificationError(
            f"transport contract mismatch: expected {config.expected_transport_contract_id}, got {contract_id}"
        )
    return QualifiedRuntimeBinding(
        executable=binary.executable,
        binary_sha256=binary.sha256,
        binary_version=binary.version,
        transport_contract_id=contract_id,
    )


@dataclass(frozen=True)
class _FakeRuntimeBinding:
    executable: str
    binary_sha256: str
    binary_version: str
    transport_contract_id: str


def _fake_runtime_binding(
    config: OpenCodeTrustedConfig,
) -> _FakeRuntimeBinding:
    """Return a receiver-compatible runtime binding without probing the real
    OpenCode binary. Used only by fake-process tests so they never touch the
    installed OpenCode executable.
    """
    return _FakeRuntimeBinding(
        executable=config.executable_path,
        binary_sha256=config.expected_sha256,
        binary_version=config.expected_version,
        transport_contract_id=config.expected_transport_contract_id,
    )


def _resolve_binding(
    config: OpenCodeTrustedConfig,
    *,
    runtime_binding: _FakeRuntimeBinding | QualifiedRuntimeBinding | None = None,
) -> _FakeRuntimeBinding | QualifiedRuntimeBinding:
    if runtime_binding is not None:
        return runtime_binding
    return qualify_opencode_runtime(config)


def _ordered_run_json_args() -> tuple[str, ...]:
    """Qualified OpenCode argv fragment for the selected transport.

    Uses ``opencode run --format json --pure``: the non-interactive
    JSONL event mode with external plugins disabled by ``--pure``.
    Input is delivered positionally; stdin is not a governed input
    channel for this adapter.
    """
    return ("run", "--format", "json", "--pure", "--agent", OPENCODE_AGENT_ID)


@dataclass(frozen=True)
class OpenCodeArgv:
    executable: str
    args: tuple[str, ...]
    cwd: str
    env: tuple[tuple[str, str], ...]
    input_schema_file: str
    spool_directory: str
    transport_contract_id: str = ""
    shell: bool = False

    def to_list(self) -> list[str]:
        return [self.executable, *self.args]

    def validate(self, config: OpenCodeTrustedConfig) -> None:
        if self.shell is not False or isinstance(self.args, str):
            raise OpenCodeTransportQualificationError(
                "structured argv with shell=False is required"
            )
        if self.executable != str(Path(config.executable_path).resolve()):
            raise OpenCodeTransportQualificationError("executable is not the verified path")
        if self.cwd != str(Path(config.working_directory).resolve()):
            raise OpenCodeTransportQualificationError("cwd differs from trusted binding")
        if self.env != config.environment:
            raise OpenCodeTransportQualificationError("environment differs from trusted binding")
        if self.transport_contract_id != config.expected_transport_contract_id:
            raise OpenCodeTransportQualificationError(
                "argv is not bound to the qualified transport contract"
            )


def build_opencode_argv(
    config: OpenCodeTrustedConfig,
    binding: QualifiedRuntimeBinding,
    *,
    runtime_run_id: str,
    task_message: str = "",
) -> OpenCodeArgv:
    config.validate()
    if (
        binding.executable != str(Path(config.executable_path).resolve())
        or binding.binary_sha256 != config.expected_sha256
        or binding.binary_version != config.expected_version
    ):
        raise OpenCodeBinaryVerificationError(
            "binary identity differs from qualified runtime binding"
        )
    if binding.transport_contract_id != config.expected_transport_contract_id:
        raise OpenCodeTransportQualificationError("unknown transport contract ID")
    if not runtime_run_id or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in runtime_run_id
    ):
        raise OpenCodeTransportQualificationError("unsafe runtime_run_id")
    spool = Path(config.spool_directory)
    # Build args with optional task message
    args = _ordered_run_json_args()
    if task_message:
        args = args + (task_message,)
    result = OpenCodeArgv(
        executable=binding.executable,
        args=args,
        cwd=str(Path(config.working_directory).resolve()),
        env=config.environment,
        input_schema_file=config.output_schema_file,
        spool_directory=str(spool),
        transport_contract_id=binding.transport_contract_id,
    )
    result.validate(config)
    return result


@dataclass(frozen=True)
class OpenCodeProcessResult:
    pid: int
    returncode: int
    stdout: str
    stderr: str
    final_output: str = ""
    timed_out: bool = False
    cancelled: bool = False
    duration_seconds: float = 0.0
    stdout_truncated: bool = False
    stdout_total_bytes: int = 0
    stderr_truncated: bool = False
    stderr_total_bytes: int = 0


class OpenCodeProcessProtocol:
    def start(self, argv: OpenCodeArgv, stdin_data: str) -> int:
        raise NotImplementedError

    def poll(self, pid: int) -> Optional[OpenCodeProcessResult]:
        raise NotImplementedError

    def terminate(self, pid: int) -> None:
        raise NotImplementedError

    def kill(self, pid: int) -> None:
        raise NotImplementedError

    @property
    def owned(self) -> bool:
        raise NotImplementedError


@dataclass
class _StreamMetadata:
    total_bytes: int = 0
    retained_bytes: int = 0
    truncated: bool = False
    error: Optional[str] = None


@dataclass
class _OwnedProcess:
    process: subprocess.Popen
    spool: Path
    stdout_path: Path
    stderr_path: Path
    started_at: float
    run_id: str
    collected: bool = False
    stdout_reader: Optional[threading.Thread] = None
    stderr_reader: Optional[threading.Thread] = None
    stdout_meta: _StreamMetadata = field(default_factory=_StreamMetadata)
    stderr_meta: _StreamMetadata = field(default_factory=_StreamMetadata)


class OpenCodeLiveProcess(OpenCodeProcessProtocol):
    """One trusted OpenCode process for the selected `run --format json --pure` transport.

    Uses concurrent stream draining via PIPE to avoid handle-inheritance
    issues with the OpenCode/Bun `run` command on Windows. Output is
    captured to spool files owned by Hermes.
    """

    STDOUT_RETENTION_LIMIT = 1024 * 1024  # 1 MiB
    STDERR_RETENTION_LIMIT = 128 * 1024   # 128 KiB

    def __init__(
        self,
        *,
        popen: Callable = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._popen = popen
        self._monotonic = monotonic
        self._owned: dict[int, _OwnedProcess] = {}

    def start(self, argv: OpenCodeArgv, stdin_data: str) -> int:
        run_id = self._upid(argv)
        spool = Path(argv.spool_directory)
        spool.mkdir(parents=True, exist_ok=True)
        output_path = spool / f"{run_id}.json"
        stdout_path = spool / f"{run_id}.stdout.jsonl"
        stderr_path = spool / f"{run_id}.stderr.txt"
        for path in (output_path, stdout_path, stderr_path):
            if path.exists():
                raise OpenCodeProcessError(f"adapter output already exists: {path}")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = self._popen(
                argv.to_list(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=argv.cwd,
                env=dict(argv.env),
                shell=False,
                creationflags=creationflags,
            )
        except Exception:
            raise
        owned = _OwnedProcess(
            process=process,
            spool=spool,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            started_at=self._monotonic(),
            run_id=run_id,
        )
        self._owned[process.pid] = owned
        # Start reader threads to concurrently drain stdout/stderr
        stdout_reader = threading.Thread(
            target=self._drain_stream,
            args=(process.stdout, stdout_path, owned.stdout_meta, self.STDOUT_RETENTION_LIMIT),
            daemon=True,
        )
        stderr_reader = threading.Thread(
            target=self._drain_stream,
            args=(process.stderr, stderr_path, owned.stderr_meta, self.STDERR_RETENTION_LIMIT),
            daemon=True,
        )
        owned.stdout_reader = stdout_reader
        owned.stderr_reader = stderr_reader
        stdout_reader.start()
        stderr_reader.start()
        return process.pid

    def _drain_stream(
        self,
        stream: BinaryIO,
        path: Path,
        meta: _StreamMetadata,
        retention_limit: int,
    ) -> None:
        """Drain a byte stream to a bounded retention file.

        Continues reading to EOF even after retention limit is reached.
        Truncation metadata is stored in the _StreamMetadata object.
        """
        total_bytes = 0
        retained_bytes = 0
        try:
            with path.open("xb") as h:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    remaining = retention_limit - retained_bytes
                    if remaining > 0:
                        if len(chunk) > remaining:
                            h.write(chunk[:remaining])
                            retained_bytes += remaining
                        else:
                            h.write(chunk)
                            retained_bytes += len(chunk)
                    # Continue reading to EOF, discarding excess bytes
        except FileExistsError:
            meta.error = "file_exists"
        except Exception as e:
            meta.error = str(e)
        finally:
            meta.total_bytes = total_bytes
            meta.retained_bytes = retained_bytes
            meta.truncated = total_bytes > retention_limit

    def poll(self, pid: int) -> Optional[OpenCodeProcessResult]:
        owned = self._owned.get(pid)
        if owned is None:
            raise OpenCodeProcessError("PID is not owned by this OpenCode process controller")
        returncode = owned.process.poll()
        if returncode is None:
            return None
        if owned.collected:
            raise OpenCodeProcessError("terminal process result was already collected")
        # Join stdout reader and verify termination
        if owned.stdout_reader is not None:
            owned.stdout_reader.join(timeout=5.0)
            if owned.stdout_reader.is_alive():
                raise OpenCodeProcessError("stdout stream capture failed: reader thread did not terminate")
        # Join stderr reader and verify termination
        if owned.stderr_reader is not None:
            owned.stderr_reader.join(timeout=5.0)
            if owned.stderr_reader.is_alive():
                raise OpenCodeProcessError("stderr stream capture failed: reader thread did not terminate")
        # Check for reader errors - capture failure even if process succeeded
        if owned.stdout_meta.error is not None:
            raise OpenCodeProcessError(f"stdout stream capture failed: {owned.stdout_meta.error}")
        if owned.stderr_meta.error is not None:
            raise OpenCodeProcessError(f"stderr stream capture failed: {owned.stderr_meta.error}")
        # All stream finalization passed - mark collected and return result
        owned.collected = True
        return OpenCodeProcessResult(
            pid=pid,
            returncode=returncode,
            stdout=self._read_bounded(owned.stdout_path, self.STDOUT_RETENTION_LIMIT),
            stderr=self._read_bounded(owned.stderr_path, self.STDERR_RETENTION_LIMIT),
            final_output=(
                self._read_bounded(owned.stdout_path, 256 * 1024)
                if (owned.stdout_path).exists()
                else ""
            ),
            duration_seconds=max(0.0, self._monotonic() - owned.started_at),
            stdout_truncated=owned.stdout_meta.truncated,
            stdout_total_bytes=owned.stdout_meta.total_bytes,
            stderr_truncated=owned.stderr_meta.truncated,
            stderr_total_bytes=owned.stderr_meta.total_bytes,
        )

    def terminate(self, pid: int) -> None:
        owned = self._owned.get(pid)
        if owned is None:
            raise OpenCodeProcessError("PID is not owned by this OpenCode process controller")
        if owned.process.poll() is None:
            owned.process.terminate()

    def kill(self, pid: int) -> None:
        owned = self._owned.get(pid)
        if owned is None:
            raise OpenCodeProcessError("PID is not owned by this OpenCode process controller")
        if owned.process.poll() is None:
            owned.process.kill()

    @property
    def owned(self) -> bool:
        return bool(self._owned)

    def _read_bounded(self, path: Path, limit: int) -> str:
        if not path.exists():
            return ""
        with path.open("rb") as h:
            data = h.read(limit + 1)
        return data.decode("utf-8", errors="replace")

    def _upid(self, argv: OpenCodeArgv) -> str:
        payload = (argv.executable, json.dumps(argv.args, sort_keys=True))
        return "run-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]


class OpenCodeFakeProcess(OpenCodeProcessProtocol):
    """Deterministic fake process for non-live `run --format json --pure` qualification.

    This exists to qualify start-state, timeout, cancellation, replay, and
    terminal-result behavior without ever submitting a real OpenCode task.
    """

    def __init__(
        self,
        *,
        sequence: Optional[list[OpenCodeProcessResult]] = None,
    ) -> None:
        self._sequence = sequence or []
        self._index = 0
        self._started = False

    def start(self, argv: OpenCodeArgv, stdin_data: str) -> int:
        self._started = True
        return 12345

    def poll(self, pid: int) -> Optional[OpenCodeProcessResult]:
        if self._index < len(self._sequence):
            result = self._sequence[self._index]
            self._index += 1
            return result
        return None

    def terminate(self, pid: int) -> None:
        pass

    def kill(self, pid: int) -> None:
        pass

    @property
    def owned(self) -> bool:
        return True


class OpenCodeReceiverAdapter:
    """Governed OpenCode receiver adapter bound to `run --format json --pure`."""

    RECEIVER_ID = "opencode-cli-agent"
    RECEIVER_CLASS = "OPENCODE"
    AGENT_ID = "hermes-ea4e-opencode-receiver"

    def __init__(
        self,
        config: Optional[OpenCodeTrustedConfig] = None,
        *,
        process_impl: Optional[OpenCodeProcessProtocol] = None,
    ) -> None:
        self._config = config or default_opencode_config()
        self._process_impl = process_impl
        self._adapter_version = PINNED_OPENCODE_ADAPTER_VERSION
        self._runtime_binding: OpenCodeFakeProcess | _FakeRuntimeBinding | None = None

    @property
    def receiver_id(self) -> str:
        return self.RECEIVER_ID

    @property
    def receiver_version(self) -> str:
        return PINNED_OPENCODE_VERSION

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    def verify_binary(self) -> BinaryIdentity:
        return resolve_pinned_binary(self._config)

    def qualify_runtime(self) -> QualifiedRuntimeBinding:
        return qualify_opencode_runtime(self._config)

    def qualify_schema_contract(self) -> dict[str, Any]:
        return {
            "schema_id": "hermes.delegation_result/v1",
            "structural_policy_id": "codex-result-structural-policy/v1",
            "qualification_version": "codex-instance-schema-qualification/v1",
        }

    def build_argv(self, runtime_run_id: str) -> Sequence[str]:
        binding = _resolve_binding(
            self._config, runtime_binding=self._runtime_binding
        )
        argv = build_opencode_argv(self._config, binding, runtime_run_id=runtime_run_id)
        return argv.to_list()

    def parse_output(self, stdout: str) -> dict[str, Any]:
        """Parse the JSONL event stream produced by ``opencode run --format json``.

        The stream is one JSON object per line. The final assistant
        text is carried by the last ``type: "text"`` event; a
        ``type: "error"`` event carries the error. If the stream is
        empty or contains no recognizable event, a parse error is
        raised so the caller can distinguish a malformed transcript
        from a genuine terminal result.

        Supports both flat (``{"type":"text","text":"..."}``) and nested
        (``{"type":"text","part":{"text":"..."}}``) text event formats.
        """
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            raise OpenCodeParseError("empty JSONL output")
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise OpenCodeParseError(f"invalid JSONL line: {exc}") from exc
        # Extract text events - support flat and nested formats
        text_events = []
        for e in events:
            if e.get("type") == "text":
                # Try flat format: {"type": "text", "text": "..."}
                text = e.get("text")
                if isinstance(text, str) and text.strip():
                    text_events.append(e)
                else:
                    # Try nested format: {"type": "text", "part": {"text": "..."}}
                    part = e.get("part")
                    if isinstance(part, dict):
                        nested_text = part.get("text")
                        if isinstance(nested_text, str) and nested_text.strip():
                            # Add flat text field for uniform access
                            e["text"] = nested_text
                            text_events.append(e)
        if text_events:
            return {"type": "text", "text": text_events[-1]["text"].strip(), "events": events}
        error_events = [e for e in events if e.get("type") == "error"]
        if error_events:
            return {"type": "error", "error": error_events[-1].get("error", {}), "events": events}
        raise OpenCodeParseError("no text or error event in JSONL output")

    def classify_start_state(
        self, pid: Optional[int], result: Optional[OpenCodeProcessResult]
    ) -> str:
        if pid is None:
            return "PREPARED"
        if result is None:
            return "DEFINITELY_STARTED"
        if result.timed_out or result.cancelled:
            return "TERMINAL"
        if result.returncode != 0:
            return "TERMINAL"
        return "TERMINAL"

    def prepare_invocation(
        self,
        *,
        idempotency_key: str,
        launch_attempt_id: str,
        delegation_id: str,
        stdin_data: str,
        task: str = "",
    ) -> tuple[InvocationRecord, Sequence[str], bool]:
        runtime_run_id = "opencode-run-" + hashlib.sha256(
            idempotency_key.encode("utf-8")
        ).hexdigest()[:32]
        binding = _resolve_binding(self._config, runtime_binding=self._runtime_binding)
        # Use task from parameter, falling back to stdin_data for backward compat
        task_text = task if task else stdin_data
        argv = build_opencode_argv(self._config, binding, runtime_run_id=runtime_run_id, task_message=task_text)
        record = InvocationRecord(
            idempotency_key=idempotency_key,
            runtime_run_id=runtime_run_id,
            start_state="PREPARED",
            terminal_state=None,
            pid=None,
            argv_hash=sha256_payload(argv.to_list()),
        )
        return record, argv.to_list(), False

    def execute(
        self,
        *,
        idempotency_key: str,
        launch_attempt_id: str,
        delegation_id: str,
        stdin_data: str,
        task: str = "",
    ) -> ExecutionOutcome:
        # Fail closed: reject empty/whitespace-only tasks before process start
        task_text = task if task else stdin_data
        if task_text.strip() == "":
            raise OpenCodeAdapterError("governed task is empty")
        record, argv_list, replayed = self.prepare_invocation(
            idempotency_key=idempotency_key,
            launch_attempt_id=launch_attempt_id,
            delegation_id=delegation_id,
            stdin_data=stdin_data,
            task=task,
        )
        if replayed:
            return ExecutionOutcome(
                process_started=False,
                replayed=True,
                record=record,
                verified_result=None,
            )
        if self._process_impl is None:
            raise OpenCodeProcessError("no process implementation available")
        argv = OpenCodeArgv(
            executable=argv_list[0],
            args=tuple(argv_list[1:]),
            cwd=self._config.working_directory,
            env=self._config.environment,
            input_schema_file=self._config.output_schema_file,
            spool_directory=self._config.spool_directory,
            transport_contract_id=self._config.expected_transport_contract_id,
        )
        pid = self._process_impl.start(argv, stdin_data)
        result = None
        timed_out = False
        start = time.monotonic()
        while True:
            if time.monotonic() - start > self._config.timeout_seconds:
                timed_out = True
                self._process_impl.terminate(pid)
                break
            result = self._process_impl.poll(pid)
            if result is not None:
                break
            time.sleep(0.05)
        if result is None:
            result = self._process_impl.poll(pid)
        if result is None:
            raise OpenCodeStartStateUnknownError("cannot classify start state")
        result = OpenCodeProcessResult(
            pid=result.pid,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            final_output=result.final_output,
            timed_out=timed_out,
            cancelled=result.cancelled,
            duration_seconds=result.duration_seconds,
        )
        terminal_state = self.classify_start_state(pid, result)
        record = InvocationRecord(
            idempotency_key=record.idempotency_key,
            runtime_run_id=record.runtime_run_id,
            start_state=record.start_state,
            terminal_state=terminal_state,
            pid=pid,
            argv_hash=record.argv_hash,
        )
        verified = None
        if terminal_state == "TERMINAL" and result.returncode == 0 and result.final_output:
            try:
                payload = self.parse_output(result.final_output)
                verified = VerifiedResult(valid=True, payload=payload)
            except OpenCodeParseError as exc:
                verified = VerifiedResult(valid=False, payload={}, parse_error=str(exc))
        return ExecutionOutcome(
            process_started=True,
            replayed=False,
            record=record,
            verified_result=verified,
        )


register_adapter("opencode-cli-agent", OpenCodeReceiverAdapter)
