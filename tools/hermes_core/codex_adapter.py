"""EA-4D.4F-R12D qualified Codex receiver boundary.

Only metadata binary verification and injected fake-process execution are
available in R12D. A live ``codex exec`` capability is deliberately absent.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

PINNED_CODEX_PATH = r"C:\Users\David\AppData\Local\OpenAI\Codex\bin\fac60c5e9a2ae3df\codex.exe"
PINNED_CODEX_SHA256 = "34e9cfe7d5bbcec306fe6ab3fd502a713a7a1f0fb644c11ad2990fc80599fd4f"
PINNED_CODEX_VERSION = "codex-cli 0.150.0-alpha.12.2"
PINNED_ADAPTER_VERSION = "1.1"
PINNED_CLI_CONTRACT_ID = "21f341c1ac959ee3a7c7ce929baf492183bd0d07e7443c0e76e4f22f0196bc02"
REGISTRY_SCHEMA_VERSION = 1
MIN_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS = 5, 60, 300
MAX_STDIN_BYTES, MAX_STDOUT_BYTES = 256 * 1024, 1024 * 1024
MAX_STDERR_BYTES, MAX_FINAL_OUTPUT_BYTES, MAX_JSONL_EVENTS = 128 * 1024, 256 * 1024, 4096
DISABLED_CAPABILITIES = (
    "shell_tool", "browser_use", "browser_use_external",
    "browser_use_full_cdp_access", "computer_use", "image_generation",
    "apps", "plugins", "hooks", "multi_agent",
)
GLOBAL_SECURITY_ARGS = ("--ask-for-approval", "never", "--sandbox", "read-only")
EXEC_BASE_ARGS = ("--json", "--ephemeral", "--ignore-user-config", "--ignore-rules")
APPROVAL_POLICY = "never"
SANDBOX_POLICY = "read-only"
AMBIENT_CONFIG_POLICY = "ignore-user-config"
STRUCTURED_OUTPUT_POLICY = "jsonl+json-schema+last-message"
INPUT_DELIVERY_POLICY = "stdin"
SUPPORTED_EVENTS = frozenset({
    "thread.started", "turn.started", "item.started", "item.updated",
    "item.completed", "turn.completed", "turn.failed", "error",
})


class CodexAdapterError(RuntimeError): pass
class BinaryVerificationError(CodexAdapterError): pass
class ArgvConstructionError(CodexAdapterError): pass
class CodexProcessError(CodexAdapterError): pass
class CodexTimeoutError(CodexAdapterError): pass
class CodexCancelledError(CodexAdapterError): pass
class CodexJsonlParseError(CodexAdapterError): pass
class CodexStartStateUnknownError(CodexAdapterError): pass
class CodexReplayConflictError(CodexAdapterError): pass
class CodexExecutionNotAuthorizedError(CodexAdapterError): pass


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_text(value: str) -> str:
    return _hash_bytes(value.encode("utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _within(path: str | Path, root: str | Path) -> Path:
    candidate, base = Path(path).resolve(strict=False), Path(root).resolve(strict=True)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ArgvConstructionError(f"path escapes trusted root: {candidate}") from exc
    return candidate


@dataclass(frozen=True)
class CodexTrustedConfig:
    executable_path: str
    expected_sha256: str
    expected_version: str
    fixture_root: str
    working_directory: str
    output_schema_file: str
    spool_directory: str
    registry_path: str
    environment: tuple[tuple[str, str], ...]
    expected_cli_contract_id: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def validate(self) -> None:
        if not Path(self.executable_path).is_absolute():
            raise BinaryVerificationError("executable path must be absolute")
        if len(self.expected_sha256) != 64:
            raise BinaryVerificationError("SHA-256 must have 64 characters")
        try: int(self.expected_sha256, 16)
        except ValueError as exc: raise BinaryVerificationError("SHA-256 is not hexadecimal") from exc
        if not self.expected_version.startswith("codex-cli "):
            raise BinaryVerificationError("version is not Codex CLI")
        if len(self.expected_cli_contract_id) != 64:
            raise ArgvConstructionError("CLI contract ID must have 64 characters")
        try: int(self.expected_cli_contract_id, 16)
        except ValueError as exc: raise ArgvConstructionError("CLI contract ID is not hexadecimal") from exc
        if not MIN_TIMEOUT_SECONDS <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise CodexTimeoutError("timeout is outside the frozen 5..300 second range")
        root = Path(self.fixture_root).resolve(strict=True)
        if not _within(self.working_directory, root).is_dir():
            raise ArgvConstructionError("trusted cwd is not a directory")
        for path in (self.output_schema_file, self.spool_directory, self.registry_path):
            _within(path, root)
        names = [name for name, _ in self.environment]
        if len(names) != len(set(names)) or "PATH" in names:
            raise ArgvConstructionError("environment must be unique and cannot inherit PATH")


def default_trusted_config() -> CodexTrustedConfig:
    root = Path(__file__).resolve().parents[2]
    runtime = root / ".hermes" / "runtime" / "ea4d4f" / "codex"
    names = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA")
    env = [(name, os.environ[name]) for name in names if os.environ.get(name)]
    env.append(("CODEX_HOME", str(Path.home() / ".codex")))
    return CodexTrustedConfig(
        PINNED_CODEX_PATH, PINNED_CODEX_SHA256, PINNED_CODEX_VERSION,
        str(root), str(root), str(runtime / "hermes-result-v1.schema.json"),
        str(runtime / "spool"), str(runtime / "transport.sqlite3"), tuple(sorted(env)),
        PINNED_CLI_CONTRACT_ID,
    )


@dataclass(frozen=True)
class CodexBinaryIdentity:
    sha256: str
    version: str
    executable: str
    size_bytes: int
    metadata_probe_spawned: bool = True


@dataclass(frozen=True)
class CodexCliContract:
    adapter_version: str
    binary_sha256: str
    binary_version: str
    global_options: tuple[str, ...]
    subcommand: str
    ordered_exec_options: tuple[str, ...]
    approval_policy: str
    sandbox_policy: str
    ambient_config_policy: str
    structured_output: str
    input_delivery: str
    disabled_capabilities: tuple[str, ...]

    def material(self) -> dict[str, Any]:
        return {
            "adapter_version": self.adapter_version,
            "ambient_config_policy": self.ambient_config_policy,
            "approval_policy": self.approval_policy,
            "binary_sha256": self.binary_sha256,
            "binary_version": self.binary_version,
            "disabled_capabilities": list(self.disabled_capabilities),
            "global_options": list(self.global_options),
            "input_delivery": self.input_delivery,
            "ordered_exec_options": list(self.ordered_exec_options),
            "sandbox_policy": self.sandbox_policy,
            "structured_output": self.structured_output,
            "subcommand": self.subcommand,
        }


@dataclass(frozen=True)
class CodexQualifiedRuntimeBinding:
    executable: str
    binary_sha256: str
    binary_version: str
    cli_contract_id: str


def _exec_option_template(disabled_capabilities=DISABLED_CAPABILITIES) -> tuple[str, ...]:
    options = [*EXEC_BASE_ARGS, "--output-schema", "<trusted-schema-file>",
               "--output-last-message", "<adapter-owned-output-file>",
               "--cd", "<trusted-working-directory>"]
    for capability in disabled_capabilities:
        options.extend(("--disable", capability))
    return (*options, "-")


def codex_cli_contract(
    binary_sha256: str,
    binary_version: str,
    *,
    global_options=GLOBAL_SECURITY_ARGS,
    ordered_exec_options=None,
    approval_policy=APPROVAL_POLICY,
    sandbox_policy=SANDBOX_POLICY,
    ambient_config_policy=AMBIENT_CONFIG_POLICY,
    disabled_capabilities=DISABLED_CAPABILITIES,
) -> CodexCliContract:
    capabilities = tuple(disabled_capabilities)
    return CodexCliContract(
        adapter_version=PINNED_ADAPTER_VERSION,
        binary_sha256=binary_sha256,
        binary_version=binary_version,
        global_options=tuple(global_options),
        subcommand="exec",
        ordered_exec_options=tuple(
            _exec_option_template(capabilities)
            if ordered_exec_options is None else ordered_exec_options
        ),
        approval_policy=approval_policy,
        sandbox_policy=sandbox_policy,
        ambient_config_policy=ambient_config_policy,
        structured_output=STRUCTURED_OUTPUT_POLICY,
        input_delivery=INPUT_DELIVERY_POLICY,
        disabled_capabilities=capabilities,
    )


def codex_cli_contract_id(contract: CodexCliContract) -> str:
    return _hash_text(_canonical(contract.material()))


VersionProbe = Callable[[str, tuple[tuple[str, str], ...], str], tuple[int, str, str]]
ParserProbe = Callable[[str, tuple[str, ...], tuple[tuple[str, str], ...], str], tuple[int, str, str]]


def _version_probe(executable: str, env: tuple[tuple[str, str], ...], cwd: str):
    result = subprocess.run(
        [executable, "--version"], cwd=cwd, env=dict(env), shell=False,
        capture_output=True, text=True, timeout=10, check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _parser_probe(executable: str, args: tuple[str, ...], env: tuple[tuple[str, str], ...], cwd: str):
    result = subprocess.run(
        [executable, *args], cwd=cwd, env=dict(env), shell=False,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, check=False,
    )
    return result.returncode, result.stdout, result.stderr


def resolve_pinned_binary(config: Optional[CodexTrustedConfig] = None, *, version_probe: VersionProbe = _version_probe):
    trusted = config or default_trusted_config()
    trusted.validate()
    executable = Path(trusted.executable_path).resolve(strict=True)
    if not executable.is_file(): raise BinaryVerificationError("pinned path is not a file")
    digest = hashlib.sha256()
    with executable.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    actual = digest.hexdigest()
    if actual != trusted.expected_sha256:
        raise BinaryVerificationError(f"SHA-256 mismatch: expected {trusted.expected_sha256}, got {actual}")
    code, stdout, stderr = version_probe(str(executable), trusted.environment, trusted.working_directory)
    if code != 0: raise BinaryVerificationError(f"version probe exited {code}: {stderr[:256]}")
    if stdout != trusted.expected_version:
        raise BinaryVerificationError(f"version mismatch: expected {trusted.expected_version!r}, got {stdout!r}")
    return CodexBinaryIdentity(actual, stdout, str(executable), executable.stat().st_size)


def qualify_codex_runtime(
    config: CodexTrustedConfig,
    *,
    version_probe: VersionProbe = _version_probe,
) -> CodexQualifiedRuntimeBinding:
    binary = resolve_pinned_binary(config, version_probe=version_probe)
    contract = codex_cli_contract(binary.sha256, binary.version)
    contract_id = codex_cli_contract_id(contract)
    if contract_id != config.expected_cli_contract_id:
        raise ArgvConstructionError(
            f"CLI contract mismatch: expected {config.expected_cli_contract_id}, got {contract_id}"
        )
    return CodexQualifiedRuntimeBinding(
        executable=binary.executable,
        binary_sha256=binary.sha256,
        binary_version=binary.version,
        cli_contract_id=contract_id,
    )


def _ordered_args(schema: Path, output: Path, working_directory: Path) -> tuple[str, ...]:
    args = [*GLOBAL_SECURITY_ARGS, "exec", *EXEC_BASE_ARGS,
            "--output-schema", str(schema), "--output-last-message", str(output),
            "--cd", str(working_directory)]
    for capability in DISABLED_CAPABILITIES:
        args.extend(("--disable", capability))
    return (*args, "-")


@dataclass(frozen=True)
class CodexArgv:
    executable: str
    args: tuple[str, ...]
    cwd: str
    env: tuple[tuple[str, str], ...]
    input_schema_file: str
    output_file: str
    cli_contract_id: str = ""
    shell: bool = False
    def to_list(self): return [self.executable, *self.args]
    def validate(self, config: CodexTrustedConfig) -> None:
        if self.shell is not False or isinstance(self.args, str):
            raise ArgvConstructionError("structured argv with shell=False is required")
        if self.executable != str(Path(config.executable_path).resolve(strict=True)):
            raise ArgvConstructionError("executable is not the verified path")
        if self.cwd != str(Path(config.working_directory).resolve(strict=True)) or self.env != config.environment:
            raise ArgvConstructionError("cwd/environment differs from trusted binding")
        if self.cli_contract_id != config.expected_cli_contract_id:
            raise ArgvConstructionError("argv is not bound to the qualified CLI contract")
        schema = _within(config.output_schema_file, config.fixture_root)
        output = _within(self.output_file, config.fixture_root)
        spool = _within(config.spool_directory, config.fixture_root)
        if self.input_schema_file != str(schema) or output.parent != spool:
            raise ArgvConstructionError("schema/output paths differ from the qualified binding")
        expected = _ordered_args(schema, output, Path(config.working_directory).resolve(strict=True))
        if self.args != expected:
            raise ArgvConstructionError("ordered argv differs from the qualified CLI contract")


def build_codex_argv(config: CodexTrustedConfig, binding: CodexQualifiedRuntimeBinding, *, runtime_run_id: str):
    config.validate()
    if (
        binding.executable != str(Path(config.executable_path).resolve(strict=True))
        or binding.binary_sha256 != config.expected_sha256
        or binding.binary_version != config.expected_version
    ):
        raise BinaryVerificationError("binary identity differs from qualified runtime binding")
    if binding.cli_contract_id != config.expected_cli_contract_id:
        raise ArgvConstructionError("unknown CLI contract ID")
    if not runtime_run_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in runtime_run_id):
        raise ArgvConstructionError("unsafe runtime_run_id")
    schema = _within(config.output_schema_file, config.fixture_root)
    output = _within(config.spool_directory, config.fixture_root) / f"{runtime_run_id}.json"
    args = _ordered_args(schema, output, Path(config.working_directory).resolve(strict=True))
    result = CodexArgv(binding.executable, args, str(Path(config.working_directory).resolve(strict=True)),
                       config.environment, str(schema), str(output), binding.cli_contract_id)
    result.validate(config)
    return result


@dataclass(frozen=True)
class CodexProcessResult:
    pid: int
    returncode: int
    stdout: str
    stderr: str
    final_output: str = ""
    timed_out: bool = False
    cancelled: bool = False
    duration_seconds: float = 0.0


class CodexProcessProtocol(Protocol):
    def start(self, argv: CodexArgv, stdin_data: str) -> int: ...
    def poll(self, pid: int) -> Optional[CodexProcessResult]: ...
    def terminate(self, pid: int) -> None: ...
    def kill(self, pid: int) -> None: ...


@dataclass(frozen=True)
class CodexJsonlEvent:
    event_type: str
    data: dict[str, Any]
    raw_line: str


@dataclass(frozen=True)
class CodexJsonlResult:
    events: tuple[CodexJsonlEvent, ...]
    terminal_event: Optional[CodexJsonlEvent]
    is_valid: bool
    error: Optional[str]


def _bad(events, message): return CodexJsonlResult(tuple(events), None, False, message)


def parse_codex_jsonl(stdout: str) -> CodexJsonlResult:
    if len(stdout.encode()) > MAX_STDOUT_BYTES: return _bad([], "stdout exceeds limit")
    lines, events, terminal = [x for x in stdout.splitlines() if x.strip()], [], None
    if not lines: return _bad([], "missing terminal event")
    if len(lines) > MAX_JSONL_EVENTS: return _bad([], "event count exceeds limit")
    thread = turn = False
    for index, line in enumerate(lines):
        try: data = json.loads(line)
        except json.JSONDecodeError as exc: return _bad(events, f"malformed JSON: {exc}")
        if not isinstance(data, dict): return _bad(events, "event is not an object")
        kind = data.get("type")
        if kind not in SUPPORTED_EVENTS: return _bad(events, f"unsupported event type: {kind!r}")
        event = CodexJsonlEvent(kind, data, line); events.append(event)
        if terminal is not None: return _bad(events, "event follows terminal event")
        if kind == "thread.started":
            if index or thread or not isinstance(data.get("thread_id"), str): return _bad(events, "invalid thread.started")
            thread = True
        elif kind == "turn.started":
            if not thread or turn: return _bad(events, "invalid turn.started ordering")
            turn = True
        elif kind.startswith("item.") and (not turn or not isinstance(data.get("item"), dict)):
            return _bad(events, "invalid item event")
        elif kind == "turn.completed":
            if not turn or not isinstance(data.get("usage"), dict): return _bad(events, "invalid turn.completed")
            terminal = event
        elif kind == "turn.failed":
            if not turn or not isinstance(data.get("error"), dict): return _bad(events, "invalid turn.failed")
            terminal = event
        elif kind == "error" and not isinstance(data.get("message"), str): return _bad(events, "invalid error event")
    return CodexJsonlResult(tuple(events), terminal, terminal is not None, None if terminal else "missing terminal event")


@dataclass(frozen=True)
class CodexVerifiedResult:
    valid: bool
    outcome: Optional[str]
    payload: Optional[dict[str, Any]]
    error: Optional[str]
    process_exit_success: bool


def validate_final_output(text: str):
    if len(text.encode()) > MAX_FINAL_OUTPUT_BYTES: return None, "final output exceeds limit"
    try: data = json.loads(text)
    except json.JSONDecodeError as exc: return None, f"invalid final JSON: {exc}"
    required = {"schema_version", "outcome", "result_payload", "output_manifest",
                "evidence_manifest", "error_code", "error_summary"}
    if not isinstance(data, dict) or set(data) != required: return None, "fields do not match pinned schema"
    if data["schema_version"] != "1" or data["outcome"] not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        return None, "incompatible schema or outcome"
    if not isinstance(data["result_payload"], dict) or not isinstance(data["output_manifest"], list) or not isinstance(data["evidence_manifest"], list):
        return None, "payload/manifests have wrong types"
    if data["outcome"] == "FAILED" and not all(isinstance(data[k], str) and data[k] for k in ("error_code", "error_summary")):
        return None, "FAILED requires error fields"
    if data["outcome"] == "SUCCEEDED" and (data["error_code"] is not None or data["error_summary"] is not None):
        return None, "SUCCEEDED cannot carry error fields"
    return data, None


def verify_process_result(result: CodexProcessResult):
    if len(result.stderr.encode()) > MAX_STDERR_BYTES: return CodexVerifiedResult(False, None, None, "stderr exceeds limit", False)
    parsed = parse_codex_jsonl(result.stdout)
    if not parsed.is_valid: return CodexVerifiedResult(False, None, None, parsed.error, result.returncode == 0)
    output, error = validate_final_output(result.final_output)
    if error: return CodexVerifiedResult(False, None, None, error, result.returncode == 0)
    terminal = parsed.terminal_event.event_type
    if (terminal == "turn.completed") != (output["outcome"] == "SUCCEEDED"):
        return CodexVerifiedResult(False, None, None, "terminal/result conflict", result.returncode == 0)
    warning = None if result.returncode == 0 else "nonzero exit with captured terminal artifact"
    return CodexVerifiedResult(True, output["outcome"], output, warning, result.returncode == 0)


@dataclass(frozen=True)
class CodexInvocationRecord:
    idempotency_key: str; material_hash: str; runtime_run_id: str
    launch_attempt_id: str; delegation_id: str; argv_hash: str
    start_state: str; terminal_state: Optional[str]; pid: Optional[int]
    result_json: Optional[str]; cancellation_reason: Optional[str]


DDL = """CREATE TABLE IF NOT EXISTS codex_transport_metadata (
schema_version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS codex_transport_invocations (
idempotency_key TEXT PRIMARY KEY, material_hash TEXT NOT NULL, runtime_run_id TEXT NOT NULL,
launch_attempt_id TEXT NOT NULL, delegation_id TEXT NOT NULL, argv_hash TEXT NOT NULL,
start_state TEXT NOT NULL, terminal_state TEXT, pid INTEGER, result_json TEXT,
cancellation_reason TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);"""


class CodexInvocationRegistry:
    def __init__(self, path: str): self.path = path
    def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript(DDL)
            row = conn.execute("SELECT schema_version FROM codex_transport_metadata").fetchone()
            if row is None:
                conn.execute("INSERT INTO codex_transport_metadata VALUES (?)", (REGISTRY_SCHEMA_VERSION,))
            elif row[0] != REGISTRY_SCHEMA_VERSION:
                raise CodexAdapterError("unsupported Codex transport registry schema")
            conn.commit()
        finally: conn.close()
    @staticmethod
    def _record(row): return CodexInvocationRecord(*row)
    def get(self, key: str):
        conn = sqlite3.connect(self.path)
        try:
            row = conn.execute("SELECT idempotency_key,material_hash,runtime_run_id,launch_attempt_id,delegation_id,argv_hash,start_state,terminal_state,pid,result_json,cancellation_reason FROM codex_transport_invocations WHERE idempotency_key=?", (key,)).fetchone()
        finally: conn.close()
        return self._record(row) if row else None
    def reserve(self, *, key, material_hash, run_id, launch_id, delegation_id, argv_hash):
        now = time.time(); conn = sqlite3.connect(self.path, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT idempotency_key,material_hash,runtime_run_id,launch_attempt_id,delegation_id,argv_hash,start_state,terminal_state,pid,result_json,cancellation_reason FROM codex_transport_invocations WHERE idempotency_key=?", (key,)).fetchone()
            if row:
                record = self._record(row)
                if record.material_hash != material_hash:
                    conn.execute("ROLLBACK"); raise CodexReplayConflictError("divergent invocation replay")
                conn.execute("COMMIT"); return record, True
            conn.execute("INSERT INTO codex_transport_invocations VALUES (?,?,?,?,?,?,'PREPARED',NULL,NULL,NULL,NULL,?,?)",
                         (key, material_hash, run_id, launch_id, delegation_id, argv_hash, now, now))
            conn.execute("COMMIT")
        finally: conn.close()
        return self.get(key), False
    def transition(self, key, *, start_state, terminal_state=None, pid=None, result_json=None, reason=None):
        conn = sqlite3.connect(self.path)
        try:
            changed = conn.execute("UPDATE codex_transport_invocations SET start_state=?,terminal_state=?,pid=COALESCE(?,pid),result_json=?,cancellation_reason=COALESCE(?,cancellation_reason),updated_at=? WHERE idempotency_key=?",
                                   (start_state, terminal_state, pid, result_json, reason, time.time(), key)).rowcount
            if changed != 1: raise CodexAdapterError("registry row missing")
            conn.commit()
        finally: conn.close()
        return self.get(key)


@dataclass(frozen=True)
class CodexStartState:
    state: str; pid: Optional[int] = None; result: Optional[CodexProcessResult] = None
    @property
    def can_invoke(self): return self.state in {"NOT_STARTED", "FAILED_BEFORE_START"}
    @property
    def is_unknown(self): return self.state == "UNKNOWN"


@dataclass(frozen=True)
class CodexExecutionOutcome:
    record: CodexInvocationRecord
    verified_result: Optional[CodexVerifiedResult]
    process_started: bool
    replayed: bool


class CodexReceiverAdapter:
    def __init__(self, *, config=None, process_impl=None, version_probe=_version_probe,
                 parser_probe=_parser_probe, monotonic=time.monotonic, sleep=time.sleep):
        self.config = config or default_trusted_config(); self.config.validate()
        self.process = process_impl; self.version_probe = version_probe; self.parser_probe = parser_probe
        self.monotonic, self.sleep = monotonic, sleep
        self.registry = CodexInvocationRegistry(self.config.registry_path)
    @property
    def timeout_seconds(self): return self.config.timeout_seconds
    def verify_binary(self): return resolve_pinned_binary(self.config, version_probe=self.version_probe)
    def qualify_runtime(self): return qualify_codex_runtime(self.config, version_probe=self.version_probe)
    def build_argv(self, runtime_run_id="codex-run-dry"):
        return build_codex_argv(self.config, self.qualify_runtime(), runtime_run_id=runtime_run_id)
    def parse_jsonl(self, stdout): return parse_codex_jsonl(stdout)
    def classify_start_state(self, pid, result):
        if pid is None and result is None: return CodexStartState("NOT_STARTED")
        if pid is not None and result is None: return CodexStartState("START_REQUESTED", pid)
        if pid is not None or (result is not None and result.pid > 0):
            return CodexStartState("DEFINITELY_STARTED", pid or result.pid, result)
        return CodexStartState("FAILED_BEFORE_START", result=result)
    def prepare_invocation(self, *, idempotency_key, launch_attempt_id, delegation_id, stdin_data, cancelled=False, revoked=False):
        if not all((idempotency_key, launch_attempt_id, delegation_id)): raise CodexAdapterError("lineage required")
        if len(stdin_data.encode()) > MAX_STDIN_BYTES: raise CodexAdapterError("stdin exceeds limit")
        self.registry.initialize(); run_id = f"codex-run-{_hash_text(idempotency_key)[:32]}"
        argv = self.build_argv(run_id); argv_hash = _hash_text(_canonical(argv.to_list()))
        material = _hash_text(_canonical({"adapter": PINNED_ADAPTER_VERSION,
            "cli_contract_id": argv.cli_contract_id, "argv": argv_hash,
            "delegation": delegation_id, "launch": launch_attempt_id,
            "stdin": _hash_text(stdin_data), "timeout": self.timeout_seconds}))
        record, replayed = self.registry.reserve(key=idempotency_key, material_hash=material,
            run_id=run_id, launch_id=launch_attempt_id, delegation_id=delegation_id, argv_hash=argv_hash)
        if (cancelled or revoked) and record.terminal_state is None:
            reason = "LEASE_REVOKED_BEFORE_EXECUTION" if revoked else "DELEGATION_CANCELLED"
            record = self.registry.transition(idempotency_key, start_state="NOT_STARTED", terminal_state="CANCELLED", reason=reason)
        return record, argv, replayed
    def request_cancellation(self, key, reason):
        record = self.registry.get(key)
        if record is None: raise CodexAdapterError("unknown invocation")
        if record.terminal_state is not None: return record
        return self.registry.transition(key, start_state=record.start_state,
            terminal_state="CANCELLED" if record.pid is None else None, reason=reason)
    @staticmethod
    def _replay_verified(record):
        if record.terminal_state != "VERIFIED" or not record.result_json: return None
        try: result = CodexProcessResult(**json.loads(record.result_json))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CodexAdapterError("durable transport result is corrupt") from exc
        verified = verify_process_result(result)
        if not verified.valid: raise CodexAdapterError("durable transport result no longer verifies")
        return verified
    def execute(self, *, idempotency_key, launch_attempt_id, delegation_id, stdin_data,
                cancelled=False, revoked=False, cancellation_check=lambda: None):
        record, argv, replayed = self.prepare_invocation(idempotency_key=idempotency_key,
            launch_attempt_id=launch_attempt_id, delegation_id=delegation_id,
            stdin_data=stdin_data, cancelled=cancelled, revoked=revoked)
        if record.terminal_state is not None or (replayed and record.start_state != "PREPARED"):
            return CodexExecutionOutcome(record, self._replay_verified(record), record.pid is not None, replayed)
        if self.process is None: raise CodexExecutionNotAuthorizedError("no process capability")
        self.registry.transition(idempotency_key, start_state="START_REQUESTED")
        try:
            pid = self.process.start(argv, stdin_data)
            if not isinstance(pid, int) or pid <= 0: raise CodexStartStateUnknownError("untrusted PID")
        except CodexStartStateUnknownError:
            record = self.registry.transition(idempotency_key, start_state="UNKNOWN")
            return CodexExecutionOutcome(record, None, False, replayed)
        except Exception as exc:
            record = self.registry.transition(idempotency_key, start_state="FAILED_BEFORE_START",
                terminal_state="FAILED_BEFORE_START", result_json=_canonical({"error": str(exc)[:512]}))
            return CodexExecutionOutcome(record, None, False, replayed)
        record = self.registry.transition(idempotency_key, start_state="DEFINITELY_STARTED", pid=pid)
        deadline = self.monotonic() + self.timeout_seconds
        while True:
            durable = self.registry.get(idempotency_key)
            reason = durable.cancellation_reason if durable else None
            reason = reason or cancellation_check()
            if reason:
                self.process.terminate(pid)
                if self.process.poll(pid) is None: self.process.kill(pid)
                record = self.registry.transition(idempotency_key, start_state="DEFINITELY_STARTED",
                    terminal_state="CANCELLED", pid=pid, reason=reason)
                return CodexExecutionOutcome(record, None, True, replayed)
            result = self.process.poll(pid)
            if result is not None:
                if result.pid != pid:
                    record = self.registry.transition(idempotency_key, start_state="UNKNOWN", pid=pid)
                    return CodexExecutionOutcome(record, None, True, replayed)
                verified = None if (result.cancelled or result.timed_out) else verify_process_result(result)
                terminal = "CANCELLED" if result.cancelled else "TIMED_OUT" if result.timed_out else "VERIFIED" if verified.valid else "FAILED"
                record = self.registry.transition(idempotency_key, start_state="DEFINITELY_STARTED",
                    terminal_state=terminal, pid=pid, result_json=_canonical(asdict(result)))
                return CodexExecutionOutcome(record, verified, True, replayed)
            if self.monotonic() >= deadline:
                self.process.terminate(pid)
                if self.process.poll(pid) is None: self.process.kill(pid)
                record = self.registry.transition(idempotency_key, start_state="DEFINITELY_STARTED", terminal_state="TIMED_OUT", pid=pid)
                return CodexExecutionOutcome(record, None, True, replayed)
            self.sleep(0.05)
    def qualify_no_live_invocation(self):
        binding = self.qualify_runtime()
        argv = build_codex_argv(self.config, binding, runtime_run_id="codex-run-dry")
        parser_args = (*argv.args[:-1], "--help")
        output_path = Path(argv.output_file)
        output_before = (
            (output_path.stat().st_size, output_path.stat().st_mtime_ns)
            if output_path.exists() else None
        )
        code, stdout, stderr = self.parser_probe(
            argv.executable, parser_args, argv.env, argv.cwd
        )
        output_after = (
            (output_path.stat().st_size, output_path.stat().st_mtime_ns)
            if output_path.exists() else None
        )
        if code != 0 or "Usage: codex exec" not in stdout:
            raise ArgvConstructionError(
                f"complete CLI contract parser qualification failed ({code}): {stderr[:256]}"
            )
        if output_before != output_after:
            raise ArgvConstructionError("parser qualification produced a task output artifact")
        return {"binary_path": binding.executable, "binary_sha256": binding.binary_sha256,
            "binary_version": binding.binary_version, "cli_contract_id": binding.cli_contract_id,
            "metadata_probe_spawned": True, "parser_probe_spawned": True,
            "parser_validation_args": [argv.executable, *parser_args],
            "approval_policy": APPROVAL_POLICY, "sandbox_policy": SANDBOX_POLICY,
            "ambient_config_policy": AMBIENT_CONFIG_POLICY,
            "human_approval_prompts": False, "automatic_operation_approval": False,
            "parser_output_artifact_changed": False,
            "model_agent_execution_possible": False, "argv": argv.to_list(),
            "environment_names": [k for k, _ in argv.env], "timeout_seconds": self.timeout_seconds,
            "disabled_capabilities": list(DISABLED_CAPABILITIES), "live_invocation": False}
