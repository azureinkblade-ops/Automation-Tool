"""Test-owned admission for two metadata nodes; no task execution authority."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from tools.hermes_core import codex_adapter as adapter
from tools.hermes_core.codex_result_schema import (
    CodexResultSchemaLineage, build_instance_bound_result_schema,
    qualify_instance_bound_result_schema,
)

PREFIX = "tests/hermes_core/test_codex_adapter.py::BinaryTests::"
NODES = {PREFIX + "test_real_requalified_binary_is_present_and_exact": 1,
         PREFIX + "test_real_complete_parser_contract_is_accepted_without_model": 2}
_real_popen = subprocess.Popen
_events = []
IDENTITY = (r"C:\Users\David\AppData\Local\OpenAI\Codex\bin\bffc5354119c8421\codex.exe",
            "081e4de4be8e38fac6ed4d95e3b1a0b9f6d31c090ddc36e1696b349fe406f575",
            "codex-cli 0.154.0-alpha.6.2",
            "c2d4912a32c00c49c1186a9d49bc7021581dbb86b9a013eaaaffd0eebd8d5a5d")


def validate(command, options, expected, environment, root, used, budget):
    if used >= budget or command != expected:
        raise ValueError("metadata argv/budget denied")
    if options.get("shell") is not False or options.get("text") is not True:
        raise ValueError("metadata shell/text denied")
    if options.get("cwd") != str(root) or options.get("env") != environment:
        raise ValueError("metadata runtime denied")
    if options.get("stdout") != subprocess.PIPE or options.get("stderr") != subprocess.PIPE:
        raise ValueError("metadata capture denied")
    if options.get("stdin") not in (None, subprocess.DEVNULL):
        raise ValueError("metadata stdin denied")
    if set(options) - {"shell", "text", "cwd", "env", "stdout", "stderr", "stdin"}:
        raise ValueError("metadata unknown options denied")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.nodeid not in NODES:
        yield
        return
    if (adapter.PINNED_CODEX_PATH, adapter.PINNED_CODEX_SHA256,
            adapter.PINNED_CODEX_VERSION, adapter.PINNED_CLI_CONTRACT_ID) != IDENTITY:
        raise RuntimeError("metadata authority identity drift")
    if hashlib.sha256(Path(adapter.PINNED_CODEX_PATH).read_bytes()).hexdigest() != adapter.PINNED_CODEX_SHA256:
        raise RuntimeError("installed metadata identity changed")
    root = item.config._tmp_path_factory.getbasetemp() / ("metadata-" + str(len(_events)))
    root.mkdir()
    (root / "home").mkdir()
    lineage = CodexResultSchemaLineage("a" * 64, "b" * 64)
    schema = build_instance_bound_result_schema(lineage)
    path = root / "result.schema.json"
    path.write_text(json.dumps(schema), encoding="ascii")
    q = qualify_instance_bound_result_schema(schema, lineage=lineage,
        binary_sha256=adapter.PINNED_CODEX_SHA256, binary_version=adapter.PINNED_CODEX_VERSION,
        cli_contract_id=adapter.PINNED_CLI_CONTRACT_ID)
    environment = {"SYSTEMROOT": os.environ["SYSTEMROOT"], "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
                   "TEMP": str(root), "TMP": str(root), "CODEX_HOME": str(root / "home")}
    original_config = adapter.default_trusted_config
    config = replace(original_config(), fixture_root=str(root), working_directory=str(root),
        output_schema_file=str(path), spool_directory=str(root / "spool"), registry_path=str(root / "transport.sqlite3"),
        environment=tuple(sorted(environment.items())), expected_schema_sha256=q.instance_schema_sha256,
        require_instance_schema_qualification=True, expected_structural_policy_id=q.structural_policy_id,
        expected_instance_schema_qualification_id=q.qualification_id,
        expected_task_input_hash=lineage.task_input_hash, expected_receiver_receipt_hash=lineage.receiver_receipt_hash)
    binding = adapter.CodexQualifiedRuntimeBinding(config.executable_path, config.expected_sha256,
                                                  config.expected_version, config.expected_cli_contract_id)
    argv = adapter.build_codex_argv(config, binding, runtime_run_id="codex-run-dry")
    commands = [[config.executable_path, "--version"], [config.executable_path, *argv.args[:-1], "--help"]]
    used = 0
    children = []

    def guarded(command, **options):
        nonlocal used
        expected = commands[used] if used < len(commands) else None
        validate(command, options, expected, environment, root, used, NODES[item.nodeid])
        used += 1
        _events.append(item.nodeid)
        options["stdin"] = subprocess.DEVNULL
        child = _real_popen(command, **options)
        children.append(child)
        return child

    original_popen, module_config = subprocess.Popen, item.module.default_trusted_config
    adapter.default_trusted_config = item.module.default_trusted_config = lambda: config
    subprocess.Popen = guarded
    try:
        yield
        assert used == NODES[item.nodeid]
        assert not Path(argv.output_file).exists()
        assert hashlib.sha256(Path(config.executable_path).read_bytes()).hexdigest() == config.expected_sha256
    finally:
        subprocess.Popen = original_popen
        adapter.default_trusted_config, item.module.default_trusted_config = original_config, module_config
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None:
                    stream.close()


def pytest_sessionfinish(session, exitstatus):
    if _events:
        print("EA4E83_METADATA_ATTEMPTS=" + str(len(_events)))
        if len(_events) != 3:
            session.exitstatus = 1
