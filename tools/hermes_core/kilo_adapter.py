"""Kilo governed receiver adapter — non-live qualification.

Selected transport: `kilo run --format json --pure --agent hermes-ea4e-kilo-receiver`

This uses the installed Kilo 7.5.6 non-interactive structured-output mode.
It does NOT open a listener socket. It emits raw JSON events on stdout for a
requested task/session.

All task-level behavior in this qualification is fake. No live model.
No live Kilo task.

``--pure`` is a PLUGIN-SUPPRESSION flag, NOT a capability deny.
From Kilo 7.5.6 source (packages/opencode/src/index.ts):

    .option("pure", {
      describe: "run without external plugins",
      type: "boolean",
    })
    .middleware(async (opts) => {
      if (opts.pure) {
        process.env.KILO_PURE = "1"
      }
    })

``--pure`` sets ``KILO_PURE=1`` to suppress external plugin loading. It does
NOT disable built-in Kilo tools from ``packages/opencode`` core (bash, edit,
read, glob, grep, MCP, session management, Agent Manager, etc.).

Hermes capability denial is achieved through:

1. Hermes task-message content controls (no task triggers mutation tools)
2. Hermes-bounded environment (HOME redirect, config isolation)
3. Hermes-owned Kilo agent profile with deny-all permissions
4. ``--pure`` plugin suppression (external tools only)
5. Hermes receiver contract design (no capability primitives exposed)

This adapter does NOT claim universal ``--auto`` or any equivalent
auto-approve flag.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
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

# Note: register_adapter is imported inside register_kilo_adapter() to avoid
# circular imports. The explicit registration is in receiver_registry.py.

PINNED_KILO_PATH = r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.5.6-win32-x64\bin\kilo.exe"
PINNED_KILO_SHA256 = "e78c0006cad1e65238e8c5b32ee937128c474f07b8d3b3fa3d0b24c32ab79860"
PINNED_KILO_VERSION = "7.5.6"
PINNED_KILO_ADAPTER_VERSION = "ea4e.3"
PINNED_KILO_TRANSPORT = "kilo-run"
KILO_AGENT_ID = "hermes-ea4e-kilo-receiver"

INPUT_DELIVERY = "positional"
STRUCTURED_OUTPUT = "jsonl"

MIN_TIMEOUT_SECONDS = 5
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 300

# Effective-home isolation policy: all Kilo config discovery roots
# are redirected under a Hermes-owned runtime boundary OUTSIDE the
# Automation Tool repository and all git worktrees.
# Kilo shares OpenCode-compatible config paths under .config/kilo/.
# Determined from os.environ["LOCALAPPDATA"] / "Hermes" / "runtime".
_HERMES_APP_DATA = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\David\AppData\Local"))
HERMES_RUNTIME_ROOT = _HERMES_APP_DATA / "Hermes" / "runtime" / "ea4e" / "kilo"
KILO_EFFECTIVE_HOME = HERMES_RUNTIME_ROOT / "home"
KILO_CONFIG_DIR = HERMES_RUNTIME_ROOT / "config"
KILO_HOME_KILO = KILO_EFFECTIVE_HOME / ".kilo"
# The out-of-repo cwd is the Hermes runtime root; no .kilo/ or .opencode/ exists there.
KILO_CWD = HERMES_RUNTIME_ROOT


def _permission_policy_material() -> dict[str, Any]:
    """Canonical permission policy material for the Kilo transport contract."""
    return {
        "global_default_deny": True,
        "permission": {
            "*": "deny",
            "read": {"*": "deny"},
            "edit": "deny",
            "write": "deny",
            "bash": "deny",
            "glob": {"*": "deny"},
            "grep": {"*": "deny"},
            "list": "deny",
            "mcp": "deny",
            "plugin": "deny",
            "agent": "deny",
            "browser": "deny",
            "web": "deny",
            "fetch": "deny",
        },
        "agents": {},
        "plugins": {},
        "mcpServers": {},
        "unknown_tool_policy": "DENY",
    }


def _build_env() -> dict[str, str]:
    """Construct a MINIMAL Hermes-owned environment for Kilo.

    The child process receives ONLY explicitly listed variables.
    No ambient parent environment is inherited.

    ACTUAL_ENV_KEY_COUNT = 16
    ENVIRONMENT_NAMES_UNIQUE = YES
    AMBIENT_KILO_ENV_INHERITED = NO
    """
    return {
        "HOME": str(KILO_EFFECTIVE_HOME),
        "USERPROFILE": str(KILO_EFFECTIVE_HOME),
        "HOMEDRIVE": "C:",
        "HOMEPATH": r"\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo\home",
        "OPENCODE_TEST_HOME": str(KILO_EFFECTIVE_HOME),
        "OPENCODE_CONFIG_DIR": str(KILO_CONFIG_DIR),
        "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
        "OPENCODE_PURE": "1",
        "KILO_CONFIG_DIR": str(KILO_CONFIG_DIR),
        "KILO_HOME": str(KILO_EFFECTIVE_HOME),
        "KILO_PURE": "1",
        "TEMP": str(KILO_EFFECTIVE_HOME / "tmp"),
        "TMP": str(KILO_EFFECTIVE_HOME / "tmp"),
        "PATH": str(Path(PINNED_KILO_PATH).resolve().parent),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "PROCESSOR_ARCHITECTURE": os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64"),
    }


def _isolation_policy_material() -> dict[str, Any]:
    """Canonical isolation policy material for the Kilo transport contract."""
    env = _build_env()
    return {
        "runtime_root": str(HERMES_RUNTIME_ROOT),
        "cwd": str(KILO_CWD),
        "effective_home": str(KILO_EFFECTIVE_HOME),
        "config_root": str(KILO_CONFIG_DIR),
        "runtime_root_within_repo": False,
        "cwd_within_repo": False,
        "environment_keys": sorted(env.keys()),
        "environment_key_count": len(env),
        "ambient_inherited": False,
        "config_isolation": "HOME, OPENCODE_CONFIG_DIR, KILO_CONFIG_DIR redirected to Hermes-controlled runtime root",
    }


def _agent_profile_hash() -> str:
    """Compute SHA-256 of the current agent profile file."""
    profile_dir = KILO_EFFECTIVE_HOME / ".kilo" / "agents" / KILO_AGENT_ID
    profile_path = profile_dir / f"{KILO_AGENT_ID}.jsonc"
    if not profile_path.exists():
        # Lazy import to create the profile if it doesn"t exist
        from tools.hermes_core.kilo_agent_profile import ensure_agent_profile
        ensure_agent_profile()
    content = profile_path.read_text(encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _canonical_material(
    binary_sha256: str,
    binary_version: str,
    *,
    transport: str = PINNED_KILO_TRANSPORT,
    pure: bool = True,
    input_delivery: str = INPUT_DELIVERY,
    structured_output: str = STRUCTURED_OUTPUT,
) -> dict[str, Any]:
    """Canonical material describing the qualified Kilo transport/interface.

    This deliberately does NOT claim a universal ``--auto`` flag.
    That permission-mode switch is dangerous and is not qualified here.
    """
    permission_material = _permission_policy_material()
    isolation_material = _isolation_policy_material()

    return {
        # Binary identity
        "adapter_version": PINNED_KILO_ADAPTER_VERSION,
        "binary_path": PINNED_KILO_PATH,
        "binary_sha256": binary_sha256,
        "binary_version": binary_version,

        # Source
        "source_commit": "fa02955bfa17b60e57e0d7406d200a73337472ee",
        "source_repository": "https://github.com/Kilo-Org/kilocode",
        "source_tag": "v7.5.6",

        # Transport interface
        "input_delivery": input_delivery,
        "pure": pure,
        "pure_semantics": "plugin-suppression only",
        "structured_output": structured_output,
        "transport": transport,

        # Fixed argv policy
        "fixed_argv_policy": [
            "<kilo_executable>", "run", "--format", "json", "--pure",
            "--agent", KILO_AGENT_ID, "--model", "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "<task_message>",
        ],
        "fixed_argv_note": "positional task input; no task-controlled flags; model fixed by Hermes; free model",

        # Receiver/agent
        "agent_id": KILO_AGENT_ID,
        "agent_profile_sha256": _agent_profile_hash(),
        "receiver_id": "kilo-cli-agent",

        # Model policy
        "model_selection_policy": "FIXED_ARGV",
        "model_flag": "--model",
        "model_value": "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "profile_model_field": "ABSENT",

        # Permission policy (hash-bound)
        "global_default_deny": True,
        "permission_policy_sha256": sha256_payload(permission_material),
        "unknown_tool_policy": "DENY",

        # Isolation policy (hash-bound)
        "ambient_inherited": False,
        "config_isolation": "HOME, OPENCODE_CONFIG_DIR, KILO_CONFIG_DIR redirected to Hermes-controlled runtime root",
        "config_root": str(KILO_CONFIG_DIR),
        "cwd": str(KILO_CWD),
        "cwd_within_repo": False,
        "effective_home": str(KILO_EFFECTIVE_HOME),
        "environment_key_count": isolation_material["environment_key_count"],
        "environment_keys": isolation_material["environment_keys"],
        "isolation_policy_sha256": sha256_payload(isolation_material),
        "runtime_root": str(HERMES_RUNTIME_ROOT),
        "runtime_root_within_repo": False,

        # Process lifecycle
        "process_primitive": "subprocess.Popen",
        "shell": False,
        "start_lifecycle": "start() -> KiloProcessHandle(pid) -> wait() -> KiloProcessResult",
        "stdin_policy": "subprocess.DEVNULL",
        "termination_policy": "terminate() + kill() supported",
        "timeout_default": DEFAULT_TIMEOUT_SECONDS,
        "timeout_max": MAX_TIMEOUT_SECONDS,
        "timeout_min": MIN_TIMEOUT_SECONDS,

        # Registry policy
        "default_receiver": False,
        "failover": "OFF",
        "production_routing": "OFF",
        "registry_policy": "explicit static initialization via _register_kilo_adapter()",
    }


KILO_TRANSPORT_CONTRACT_ID = sha256_payload(
    _canonical_material(PINNED_KILO_SHA256, PINNED_KILO_VERSION)
)


class KiloAdapterError(RuntimeError):
    pass


class KiloBinaryVerificationError(KiloAdapterError, BinaryVerificationError):
    pass


class KiloTransportQualificationError(KiloAdapterError):
    pass


class KiloProcessError(KiloAdapterError, ReceiverProcessError):
    pass


class KiloTimeoutError(KiloAdapterError, ReceiverTimeoutError):
    pass


def resolve_pinned_binary(config: dict[str, Any]) -> BinaryIdentity:
    executable = config.get("kilo_executable", PINNED_KILO_PATH)
    expected_sha = config.get("kilo_sha256", PINNED_KILO_SHA256)
    expected_version = config.get("kilo_version", PINNED_KILO_VERSION)
    path = Path(executable).resolve()
    if not path.exists():
        raise KiloBinaryVerificationError(f"Kilo executable not found: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as h:
        for chunk in iter(lambda: h.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha = digest.hexdigest()
    if actual_sha != expected_sha:
        raise KiloBinaryVerificationError(
            f"Kilo binary SHA mismatch: expected {expected_sha}, got {actual_sha}"
        )
    return BinaryIdentity(
        sha256=expected_sha,
        version=expected_version,
        executable=str(path),
        size_bytes=path.stat().st_size,
        metadata_probe_spawned=False,
    )


def build_kilo_argv(config: dict[str, Any], runtime_binding: dict[str, Any], runtime_run_id: str) -> Any:
    """Build a fixed, governed argv list for Kilo.

    The invocation is deterministic and does not accept task-controlled
    agent, model, or auto-approve overrides from the caller.
    """
    message = config.get("task_message", "")
    if not isinstance(message, str):
        raise KiloAdapterError("task_message must be a string")

    # Input hardening: reject option-looking strings and embedded newlines/quotes
    if "\n" in message or "\r" in message or "\x00" in message:
        raise KiloAdapterError("task_message contains embedded control characters")
    if message.startswith("-") or message.startswith("/"):
        raise KiloAdapterError("task_message starts with an option-looking prefix")
    if '"' in message or "'" in message:
        raise KiloAdapterError("task_message contains quotes")
    if len(message.encode("utf-8")) > 32768:
        raise KiloAdapterError("task_message exceeds 32768-byte limit")

    # Fixed argv: pinned executable, positional message, --format json, --pure, --agent, --model
    # Model and agent selection are FIXED by Hermes-owned argv.
    # --auto is NEVER used (dangerous).
    argv = [
        str(Path(config.get("kilo_executable", PINNED_KILO_PATH)).resolve()),
        "run",
        "--format",
        "json",
        "--pure",
        "--agent",
        "hermes-ea4e-kilo-receiver",
        "--model",
        "kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        message,
    ]

    class ArgvList(Sequence[str]):
        def __getitem__(self, idx):
            return argv[idx]
        def __len__(self):
            return len(argv)
        def to_list(self):
            return list(argv)
    return ArgvList()


class KiloOutputParser:
    """Parse the JSONL event stream produced by ``kilo run --format json``.

    The stream is one JSON object per line. The final assistant
    text is carried by the last ``type: "text"`` event; a
    ``type: "error"`` event carries the error. If the stream is
    empty or contains no recognizable event, a parse error is
    raised so the caller can distinguish a malformed transcript
    from a genuine terminal result.
    """

    @staticmethod
    def parse_output(stdout: str) -> dict[str, Any]:
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            raise KiloParseError("empty JSONL output")
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise KiloParseError(f"invalid JSONL line: {exc}") from exc
        text_events = [e for e in events if e.get("type") == "text" and isinstance(e.get("text"), str) and e["text"].strip()]
        if text_events:
            return {"type": "text", "text": text_events[-1]["text"].strip(), "events": events}
        error_events = [e for e in events if e.get("type") == "error"]
        if error_events:
            return {"type": "error", "error": error_events[-1].get("error", {}), "events": events}
        raise KiloParseError("no text or error event in JSONL output")


class KiloParseError(KiloAdapterError, ReceiverParseError):
    pass


class KiloProcessResult:
    """Lightweight result container for Kilo subprocess execution."""
    def __init__(self, pid: int, returncode: int, stdout: str, stderr: str, timed_out: bool = False):
        self.pid = pid
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out


class KiloProcessController:
    """Controlled subprocess execution for Kilo with shell=False."""

    def __init__(self, config: dict[str, Any]):
        self._config = config

    def _build_env(self) -> dict[str, str]:
        """Construct a MINIMAL Hermes-owned environment for Kilo.

        The child process receives ONLY explicitly listed variables.
        No ambient parent environment is inherited.

        ACTUAL_ENV_KEY_COUNT = 16
        ENVIRONMENT_NAMES_UNIQUE = YES
        AMBIENT_KILO_ENV_INHERITED = NO
        """
        return {
            "HOME": str(KILO_EFFECTIVE_HOME),
            "USERPROFILE": str(KILO_EFFECTIVE_HOME),
            "HOMEDRIVE": "C:",
            "HOMEPATH": r"\Users\David\AppData\Local\Hermes\runtime\ea4e\kilo\home",

            "OPENCODE_TEST_HOME": str(KILO_EFFECTIVE_HOME),
            "OPENCODE_CONFIG_DIR": str(KILO_CONFIG_DIR),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_PURE": "1",
            "KILO_CONFIG_DIR": str(KILO_CONFIG_DIR),
            "KILO_HOME": str(KILO_EFFECTIVE_HOME),
            "KILO_PURE": "1",
            "TEMP": str(KILO_EFFECTIVE_HOME / "tmp"),
            "TMP": str(KILO_EFFECTIVE_HOME / "tmp"),
            "PATH": str(Path(PINNED_KILO_PATH).resolve().parent),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "PROCESSOR_ARCHITECTURE": os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64"),
        }

    def start(self, argv: Sequence[str], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> KiloProcessHandle:
        """Start Kilo as a non-blocking subprocess.

        Returns a KiloProcessHandle that can be polled, terminated, or killed.
        The caller MUST call wait() or kill() to avoid zombie processes.
        """
        env = self._build_env()
        cwd = str(KILO_CWD)
        try:
            proc = subprocess.Popen(
                list(argv),
                cwd=cwd,
                env=env,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
        except Exception as exc:
            raise KiloProcessError(f"Failed to start Kilo: {exc}") from exc
        if proc.pid == 0:
            raise KiloProcessError("Kilo process started but PID is 0")
        return KiloProcessHandle(
            proc=proc,
            timeout=timeout,
            _stdout=b"",
            _stderr=b"",
            _finished=False,
        )

    def execute(self, argv: Sequence[str], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> KiloProcessResult:
        """Execute Kilo with shell=False, deterministic cwd and env.

        Blocking wrapper around start()+wait() for compatibility with
        existing call sites. For non-blocking operation, use start()
        and KiloProcessHandle.wait() instead.
        """
        handle = self.start(argv, timeout=timeout)
        try:
            result = handle.wait()
        except Exception:
            handle.kill()
            raise
        return result


@dataclass
class KiloProcessHandle:
    """A running Kilo subprocess handle with poll/terminate/kill support.

    OWNING PROCESS: The Hermes Python process that created this handle.
    The subprocess is a child of that process.

    This replaces the previous blocking-only subprocess.run() model so
    that START can be observed before TERMINAL, and cancellation can
    be attempted before the process reaches a terminal state.
    """

    proc: subprocess.Popen
    timeout: int
    _stdout: bytes = b""
    _stderr: bytes = b""
    _finished: bool = False

    @property
    def pid(self) -> int:
        return self.proc.pid

    def poll(self) -> Optional[int]:
        """Return the exit code if the process has terminated, else None."""
        if self._finished:
            return self.proc.returncode
        code = self.proc.poll()
        if code is not None:
            self._finished = True
            self._collect_output()
        return code

    def terminate(self) -> None:
        """Request graceful termination (SIGTERM on Unix, TerminateProcess on Windows)."""
        if not self._finished:
            self.proc.terminate()

    def kill(self) -> None:
        """Force-kill the process (SIGKILL on Unix, TerminateProcess on Windows)."""
        if not self._finished:
            self.proc.kill()

    def wait(self) -> "KiloProcessResult":
        """Blocking wait for the process to finish; returns KiloProcessResult."""
        try:
            stdout, stderr = self.proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            self._stdout = exc.stdout or b""
            self._stderr = exc.stderr or b""
            self._finished = True
            return KiloProcessResult(
                pid=self.pid,
                returncode=-1,
                stdout=self._stdout.decode("utf-8", errors="replace"),
                stderr=self._stderr.decode("utf-8", errors="replace"),
                timed_out=True,
            )
        self._finished = True
        self._stdout = stdout or b""
        self._stderr = stderr or b""
        return KiloProcessResult(
            pid=self.pid,
            returncode=self.proc.returncode,
            stdout=self._stdout.decode("utf-8", errors="replace"),
            stderr=self._stderr.decode("utf-8", errors="replace"),
            timed_out=False,
        )

    def _collect_output(self) -> None:
        """Best-effort collection of already-buffered output after early termination."""
        try:
            remaining_stdout, remaining_stderr = self.proc.communicate(timeout=1)
            if remaining_stdout:
                self._stdout += remaining_stdout
            if remaining_stderr:
                self._stderr += remaining_stderr
        except (subprocess.TimeoutExpired, Exception):
            pass


@dataclass(frozen=True)
class KiloRuntimeBinding:
    executable: str
    binary_sha256: str
    binary_version: str
    transport_contract_id: str
    runtime_root: str
    permission_policy_sha256: str = ""
    isolation_policy_sha256: str = ""
    agent_profile_sha256: str = ""


class KiloAdapter:
    """Kilo governed receiver adapter — non-live qualification."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self._config = config or {}
        self._binary_identity = resolve_pinned_binary(self._config)
        self._runtime_binding = KiloRuntimeBinding(
            executable=str(Path(self._config.get("kilo_executable", PINNED_KILO_PATH)).resolve()),
            binary_sha256=PINNED_KILO_SHA256,
            binary_version=PINNED_KILO_VERSION,
            transport_contract_id=KILO_TRANSPORT_CONTRACT_ID,
            runtime_root=str(HERMES_RUNTIME_ROOT),
        )
        self._adapter_version = PINNED_KILO_ADAPTER_VERSION
        self._process_controller = KiloProcessController(self._config)
        self._output_parser = KiloOutputParser()

    @property
    def receiver_id(self) -> str:
        return "kilo-cli-agent"

    @property
    def receiver_class(self) -> str:
        return "KILO"

    @property
    def receiver_version(self) -> str:
        return PINNED_KILO_VERSION

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    def verify_binary(self) -> BinaryIdentity:
        return self._binary_identity

    def qualify_runtime(self) -> KiloRuntimeBinding:
        return self._runtime_binding

    def qualify_schema_contract(self) -> dict[str, Any]:
        return {
            "schema_id": "hermes.delegation_result/v1",
            "structural_policy_id": "codex-result-structural-policy/v1",
            "qualification_version": "codex-instance-schema-qualification/v1",
        }

    def build_argv(self, runtime_run_id: str) -> Sequence[str]:
        return build_kilo_argv(self._config, {}, runtime_run_id)

    def parse_output(self, stdout: str) -> dict[str, Any]:
        return self._output_parser.parse_output(stdout)

    def classify_start_state(
        self, pid: Optional[int], result: Optional[KiloProcessResult]
    ) -> str:
        # pid is None only in prepare_invocation (pre-launch), not after execute
        if pid is None:
            return "start_state_unknown"
        if result is None:
            return "start_state_unknown"
        # pid == 0 means the process was never started (should not happen post-Popen)
        if pid == 0:
            return "start_state_unknown"
        if result.timed_out:
            return "timeout"
        if result.returncode != 0:
            return "error"
        return "started"

    def prepare_invocation(
        self, *, idempotency_key: str, launch_attempt_id: str,
        delegation_id: str, stdin_data: str,
    ) -> tuple[InvocationRecord, Sequence[str], bool]:
        if stdin_data and stdin_data.strip():
            raise KiloAdapterError("stdin not supported for Kilo positional transport")
        argv = self.build_argv("")
        record = InvocationRecord(
            idempotency_key=idempotency_key,
            runtime_run_id=launch_attempt_id,
            start_state="launched",
            terminal_state=None,
            pid=None,
            argv_hash=sha256_payload(list(argv)),
        )
        return record, argv, True

    def execute(
        self, *, idempotency_key: str, launch_attempt_id: str,
        delegation_id: str, stdin_data: str,
    ) -> ExecutionOutcome:
        argv = self.build_argv("")
        result = self._process_controller.execute(argv)
        start_state = self.classify_start_state(result.pid, result)
        record = InvocationRecord(
            idempotency_key=idempotency_key,
            runtime_run_id=launch_attempt_id,
            start_state=start_state,
            terminal_state="completed" if result.returncode == 0 else "error",
            pid=result.pid,
            argv_hash=sha256_payload(list(argv)),
        )
        verified_result = None
        if result.stdout.strip():
            try:
                parsed = self.parse_output(result.stdout)
                verified_result = VerifiedResult(valid=True, payload=parsed)
            except KiloParseError:
                verified_result = VerifiedResult(valid=False, payload={})
        # process_started=True means the process was launched (pid > 0),
        # NOT that it completed successfully. Terminal state is in the record.
        process_started = result.pid > 0
        return ExecutionOutcome(
            process_started=process_started,
            replayed=False,
            record=record,
            verified_result=verified_result,
        )


def register_kilo_adapter() -> None:
    """Register the Kilo adapter in the static receiver registry.

    This function is NOT called at import time. Registration is now
    performed explicitly in ``receiver_registry.py`` to avoid import
    side effects that mutate global registry state.
    """
    register_adapter("kilo-cli-agent", KiloAdapter)
