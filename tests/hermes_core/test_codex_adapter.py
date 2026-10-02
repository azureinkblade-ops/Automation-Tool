"""R12D qualification tests. No live Codex agent task is launched."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.hermes_core.codex_adapter import (
    GLOBAL_SECURITY_ARGS,
    MAX_JSONL_EVENTS,
    MAX_STDOUT_BYTES,
    PINNED_CODEX_PATH,
    PINNED_CODEX_SHA256,
    PINNED_CODEX_VERSION,
    PINNED_CLI_CONTRACT_ID,
    EARLIER_QUALIFIED_CODEX_SHA256,
    EARLIER_QUALIFIED_CODEX_VERSION,
    EARLIER_QUALIFIED_CLI_CONTRACT_ID,
    PREVIOUS_QUALIFIED_CODEX_SHA256,
    PREVIOUS_QUALIFIED_CODEX_VERSION,
    PREVIOUS_QUALIFIED_CLI_CONTRACT_ID,
    ArgvConstructionError,
    BinaryVerificationError,
    CodexAdapterError,
    CodexBinaryIdentity,
    CodexExecutionNotAuthorizedError,
    CodexProcessResult,
    CodexReceiverAdapter,
    CodexReplayConflictError,
    CodexStartStateUnknownError,
    CodexTimeoutError,
    CodexTrustedConfig,
    build_codex_argv,
    codex_cli_contract,
    codex_cli_contract_id,
    default_trusted_config,
    parse_codex_jsonl,
    qualify_codex_result_schema_material,
    resolve_pinned_binary,
    validate_final_output,
    verify_process_result,
)


def success_jsonl():
    return "\n".join((
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        json.dumps({"type": "turn.started"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}),
    ))


def failed_jsonl():
    return "\n".join((
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        json.dumps({"type": "turn.started"}),
        json.dumps({"type": "turn.failed", "error": {"message": "failed"}}),
    ))


def final_output(outcome="SUCCEEDED"):
    failed = outcome == "FAILED"
    return json.dumps({
        "schema_version": "1", "outcome": outcome,
        "result_payload": {"value": "deterministic"},
        "output_manifest": [], "evidence_manifest": [],
        "error_code": "FIXTURE_FAILED" if failed else None,
        "error_summary": "fixture failed" if failed else None,
    })


class Clock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class FakeProcess:
    def __init__(self, polls=None, start_error=None, pid=421):
        self.polls = list(polls or [])
        self.start_error = start_error
        self.pid = pid
        self.starts = self.terminates = self.kills = 0
        self.argv = self.stdin = None
    def start(self, argv, stdin_data):
        self.starts += 1; self.argv, self.stdin = argv, stdin_data
        if self.start_error: raise self.start_error
        return self.pid
    def poll(self, pid): return self.polls.pop(0) if self.polls else None
    def terminate(self, pid): self.terminates += 1
    def kill(self, pid): self.kills += 1


class AdapterFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        executable = root / "Codex Bin" / "codex.exe"
        executable.parent.mkdir(); executable.write_bytes(b"qualified fake codex bytes")
        (root / "work").mkdir(); (root / "runtime").mkdir()
        schema = {
            "type": "object", "additionalProperties": False,
            "required": ["value"],
            "properties": {"value": {"type": "string"}},
        }
        schema_file = root / "runtime" / "result schema.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        self.config = CodexTrustedConfig(
            executable_path=str(executable),
            expected_sha256=__import__("hashlib").sha256(executable.read_bytes()).hexdigest(),
            expected_version=PINNED_CODEX_VERSION,
            fixture_root=str(root), working_directory=str(root / "work"),
            output_schema_file=str(schema_file),
            spool_directory=str(root / "runtime" / "spool files"),
            registry_path=str(root / "runtime" / "transport.sqlite3"),
            environment=(("CODEX_HOME", str(root / "codex-home")), ("SYSTEMROOT", r"C:\Windows")),
            expected_cli_contract_id=codex_cli_contract_id(codex_cli_contract(
                __import__("hashlib").sha256(executable.read_bytes()).hexdigest(),
                PINNED_CODEX_VERSION,
            )),
            expected_schema_sha256=qualify_codex_result_schema_material(schema).schema_sha256,
        )
        self.probes = self.parser_probes = 0
    def tearDown(self): self.tmp.cleanup()
    def probe(self, executable, environment, cwd):
        self.probes += 1
        self.assertEqual(executable, str(Path(self.config.executable_path).resolve()))
        self.assertEqual(environment, self.config.environment)
        self.assertEqual(cwd, self.config.working_directory)
        return 0, self.config.expected_version, ""
    def parser_probe(self, executable, args, environment, cwd):
        self.parser_probes += 1
        self.assertEqual(executable, str(Path(self.config.executable_path).resolve()))
        self.assertEqual(environment, self.config.environment)
        self.assertEqual(cwd, self.config.working_directory)
        self.assertEqual(args[-1], "--help")
        self.assertNotIn("-", args)
        return 0, "Usage: codex exec [OPTIONS] [PROMPT]", ""
    def adapter(self, process=None, config=None, clock=None):
        clock = clock or Clock()
        return CodexReceiverAdapter(config=config or self.config, process_impl=process,
            version_probe=self.probe, parser_probe=self.parser_probe,
            monotonic=clock.monotonic, sleep=clock.sleep)
    def execute(self, adapter, **kwargs):
        values = dict(idempotency_key="idem-1", launch_attempt_id="launch-1",
                      delegation_id="delegation-1", stdin_data='{"task":"read-only"}')
        values.update(kwargs); return adapter.execute(**values)


class BinaryTests(AdapterFixture):
    def test_real_requalified_binary_is_present_and_exact(self):
        identity = resolve_pinned_binary(default_trusted_config())
        self.assertEqual(identity.executable, str(Path(PINNED_CODEX_PATH).resolve()))
        self.assertEqual(identity.sha256, PINNED_CODEX_SHA256)
        self.assertEqual(identity.version, PINNED_CODEX_VERSION)
        self.assertEqual(identity.size_bytes, 313790256)
    def test_actual_bytes_are_hashed(self):
        identity = resolve_pinned_binary(self.config, version_probe=self.probe)
        self.assertEqual(identity.sha256, self.config.expected_sha256)
        self.assertEqual(self.probes, 1)
    def test_hash_mismatch_fails_before_probe(self):
        with self.assertRaises(BinaryVerificationError):
            resolve_pinned_binary(replace(self.config, expected_sha256="0" * 64), version_probe=self.probe)
        self.assertEqual(self.probes, 0)
    def test_historical_binary_identity_is_not_the_successor_qualification(self):
        config = replace(
            default_trusted_config(),
            expected_sha256=PREVIOUS_QUALIFIED_CODEX_SHA256,
            expected_version=PREVIOUS_QUALIFIED_CODEX_VERSION,
        )
        with self.assertRaisesRegex(BinaryVerificationError, "SHA-256 mismatch"):
            resolve_pinned_binary(config, version_probe=self.probe)
        self.assertEqual(self.probes, 0)
    def test_version_mismatch_fails(self):
        def bad(*_): return 0, "codex-cli 0.0.0", ""
        with self.assertRaises(BinaryVerificationError): resolve_pinned_binary(self.config, version_probe=bad)
    def test_metadata_probe_failure_fails(self):
        def bad(*_): return 2, "", "bad"
        with self.assertRaises(BinaryVerificationError): resolve_pinned_binary(self.config, version_probe=bad)
    def test_missing_binary_fails(self):
        with self.assertRaises(FileNotFoundError):
            resolve_pinned_binary(replace(self.config, executable_path=str(Path(self.tmp.name) / "missing.exe")), version_probe=self.probe)
    def test_relative_binary_rejected(self):
        with self.assertRaises(BinaryVerificationError): replace(self.config, executable_path="codex.exe").validate()
    def test_arbitrary_override_api_absent(self):
        with self.assertRaises(TypeError): resolve_pinned_binary(executable="evil.exe")
    def test_real_complete_parser_contract_is_accepted_without_model(self):
        report = CodexReceiverAdapter().qualify_no_live_invocation()
        self.assertEqual(report["cli_contract_id"], PINNED_CLI_CONTRACT_ID)
        self.assertTrue(report["parser_probe_spawned"])
        self.assertFalse(report["model_agent_execution_possible"])


class BindingTests(AdapterFixture):
    def assert_args_rejected(self, args):
        argv = self.adapter().build_argv()
        with self.assertRaises(ArgvConstructionError):
            replace(argv, args=tuple(args)).validate(self.config)

    def test_argv_uses_absolute_verified_binary(self):
        argv = self.adapter().build_argv()
        self.assertTrue(Path(argv.executable).is_absolute()); self.assertNotEqual(argv.executable, "codex.exe")
    def test_windows_paths_remain_single_arguments(self):
        argv = self.adapter().build_argv()
        self.assertIn(self.config.working_directory, argv.args); self.assertIn("Codex Bin", argv.executable)
    def test_frozen_flags_are_present(self):
        args = self.adapter().build_argv().args
        for value in ("exec", "--json", "--output-schema", "--output-last-message",
                      "--ephemeral", "--ignore-user-config", "--ignore-rules",
                      "--ask-for-approval", "never", "--sandbox", "read-only", "--cd", "-"):
            self.assertIn(value, args)
    def test_global_security_options_precede_exec(self):
        args = self.adapter().build_argv().args
        self.assertEqual(args[:5], (*GLOBAL_SECURITY_ARGS, "exec"))
    def test_exec_options_and_config_isolation_follow_exec(self):
        args = self.adapter().build_argv().args; exec_index = args.index("exec")
        for option in ("--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                       "--output-schema", "--output-last-message", "--cd"):
            self.assertGreater(args.index(option), exec_index)
    def test_exact_flattened_argv_is_deterministic(self):
        self.assertEqual(self.adapter().build_argv().to_list(), self.adapter().build_argv().to_list())
    def test_historical_post_exec_approval_order_is_rejected(self):
        args = list(self.adapter().build_argv().args)
        del args[:4]; args[1:1] = ["--ask-for-approval", "never", "--sandbox", "read-only"]
        self.assert_args_rejected(args)
    def test_missing_approval_policy_is_rejected(self):
        args = list(self.adapter().build_argv().args); del args[:2]; self.assert_args_rejected(args)
    def test_wrong_approval_policy_is_rejected(self):
        args = list(self.adapter().build_argv().args); args[1] = "on-request"; self.assert_args_rejected(args)
    def test_missing_read_only_sandbox_is_rejected(self):
        args = list(self.adapter().build_argv().args); del args[2:4]; self.assert_args_rejected(args)
    def test_workspace_write_is_rejected(self):
        args = list(self.adapter().build_argv().args); args[3] = "workspace-write"; self.assert_args_rejected(args)
    def test_danger_full_access_is_rejected(self):
        args = list(self.adapter().build_argv().args); args[3] = "danger-full-access"; self.assert_args_rejected(args)
    def test_dangerous_bypass_is_rejected(self):
        args = list(self.adapter().build_argv().args); args.insert(0, "--dangerously-bypass-approvals-and-sandbox"); self.assert_args_rejected(args)
    def test_approve_for_me_is_rejected(self):
        args = list(self.adapter().build_argv().args); args.insert(0, "--approve-for-me"); self.assert_args_rejected(args)
    def test_missing_user_config_isolation_is_rejected(self):
        args = list(self.adapter().build_argv().args); args.remove("--ignore-user-config"); self.assert_args_rejected(args)
    def test_every_capability_is_disabled(self):
        args = self.adapter().build_argv().args
        for cap in ("shell_tool", "browser_use", "computer_use", "image_generation", "multi_agent"):
            self.assertIn(cap, args)
    def test_environment_is_allowlisted_without_path(self):
        argv = self.adapter().build_argv()
        self.assertEqual(argv.env, self.config.environment); self.assertNotIn("PATH", dict(argv.env))
    def test_caller_cannot_supply_cwd_or_env(self):
        with self.assertRaises(TypeError): self.adapter().build_argv(cwd=r"C:\escape", env={"PATH": "evil"})
    def test_path_escape_rejected(self):
        bad = replace(self.config, spool_directory=str(Path(self.tmp.name).parent / "escape"))
        with self.assertRaises(ArgvConstructionError): bad.validate()
    def test_path_in_env_is_rejected(self):
        with self.assertRaises(ArgvConstructionError): replace(self.config, environment=(("PATH", "evil"),)).validate()
    def test_timeout_minimum_rejected(self):
        with self.assertRaises(CodexTimeoutError): replace(self.config, timeout_seconds=4).validate()
    def test_timeout_maximum_rejected(self):
        with self.assertRaises(CodexTimeoutError): replace(self.config, timeout_seconds=301).validate()
    def test_timeout_bounds_are_accepted(self):
        replace(self.config, timeout_seconds=5).validate(); replace(self.config, timeout_seconds=300).validate()
    def test_runtime_id_cannot_escape_spool(self):
        binding = self.adapter().qualify_runtime()
        with self.assertRaises(ArgvConstructionError): build_codex_argv(self.config, binding, runtime_run_id="../bad")
    def test_shell_is_always_false(self): self.assertFalse(self.adapter().build_argv().shell)


class CliContractTests(AdapterFixture):
    def contract(self, **changes):
        return codex_cli_contract(self.config.expected_sha256, self.config.expected_version, **changes)
    def test_pinned_production_contract_id_is_stable(self):
        contract = codex_cli_contract(PINNED_CODEX_SHA256, PINNED_CODEX_VERSION)
        self.assertEqual(codex_cli_contract_id(contract), PINNED_CLI_CONTRACT_ID)
    def test_successor_contract_is_distinct_from_historical_qualification(self):
        historical = codex_cli_contract(
            PREVIOUS_QUALIFIED_CODEX_SHA256,
            PREVIOUS_QUALIFIED_CODEX_VERSION,
        )
        self.assertEqual(
            codex_cli_contract_id(historical),
            PREVIOUS_QUALIFIED_CLI_CONTRACT_ID,
        )
        self.assertNotEqual(PINNED_CLI_CONTRACT_ID, PREVIOUS_QUALIFIED_CLI_CONTRACT_ID)
        earlier = codex_cli_contract(
            EARLIER_QUALIFIED_CODEX_SHA256,
            EARLIER_QUALIFIED_CODEX_VERSION,
        )
        self.assertEqual(
            codex_cli_contract_id(earlier),
            EARLIER_QUALIFIED_CLI_CONTRACT_ID,
        )
        self.assertNotEqual(PINNED_CLI_CONTRACT_ID, EARLIER_QUALIFIED_CLI_CONTRACT_ID)
    def test_same_material_has_same_contract_id(self):
        self.assertEqual(codex_cli_contract_id(self.contract()), codex_cli_contract_id(self.contract()))
    def test_global_option_order_changes_contract_id(self):
        changed = self.contract(global_options=("--sandbox", "read-only", "--ask-for-approval", "never"))
        self.assertNotEqual(codex_cli_contract_id(changed), self.config.expected_cli_contract_id)
    def test_exec_option_order_changes_contract_id(self):
        options = list(self.contract().ordered_exec_options); options[0], options[1] = options[1], options[0]
        changed = self.contract(ordered_exec_options=options)
        self.assertNotEqual(codex_cli_contract_id(changed), self.config.expected_cli_contract_id)
    def test_approval_policy_changes_contract_id(self):
        changed = self.contract(approval_policy="on-request")
        self.assertNotEqual(codex_cli_contract_id(changed), self.config.expected_cli_contract_id)
    def test_sandbox_policy_changes_contract_id(self):
        changed = self.contract(sandbox_policy="workspace-write")
        self.assertNotEqual(codex_cli_contract_id(changed), self.config.expected_cli_contract_id)
    def test_ambient_config_policy_changes_contract_id(self):
        changed = self.contract(ambient_config_policy="inherit-user-config")
        self.assertNotEqual(codex_cli_contract_id(changed), self.config.expected_cli_contract_id)
    def test_unknown_contract_id_fails_closed(self):
        binding = self.adapter().qualify_runtime()
        with self.assertRaises(ArgvConstructionError):
            build_codex_argv(self.config, replace(binding, cli_contract_id="0" * 64), runtime_run_id="codex-run-dry")
    def test_expected_unknown_contract_fails_qualification(self):
        config = replace(self.config, expected_cli_contract_id="0" * 64)
        with self.assertRaises(ArgvConstructionError): self.adapter(config=config).qualify_runtime()
    def test_binary_and_contract_binding_rejects_binary_mismatch(self):
        binding = self.adapter().qualify_runtime()
        with self.assertRaises(BinaryVerificationError):
            build_codex_argv(self.config, replace(binding, binary_sha256="0" * 64), runtime_run_id="codex-run-dry")
    def test_historical_order_fails_before_process_capability(self):
        process = FakeProcess(); argv = self.adapter(process).build_argv()
        old = ("exec", "--ask-for-approval", "never", "--sandbox", "read-only", *argv.args[5:])
        with self.assertRaises(ArgvConstructionError): replace(argv, args=old).validate(self.config)
        self.assertEqual(process.starts, 0)


class JsonlTests(unittest.TestCase):
    def test_valid_success_stream(self): self.assertTrue(parse_codex_jsonl(success_jsonl()).is_valid)
    def test_valid_failure_stream(self): self.assertTrue(parse_codex_jsonl(failed_jsonl()).is_valid)
    def test_malformed_json_rejected(self): self.assertIn("malformed", parse_codex_jsonl('{"type":').error)
    def test_unknown_event_rejected(self):
        text = json.dumps({"type":"thread.started","thread_id":"t"})+"\n"+json.dumps({"type":"mystery"})
        self.assertIn("unsupported", parse_codex_jsonl(text).error)
    def test_missing_type_rejected(self): self.assertIn("unsupported", parse_codex_jsonl("{}").error)
    def test_missing_terminal_rejected(self):
        self.assertIn("missing terminal", parse_codex_jsonl(json.dumps({"type":"thread.started","thread_id":"t"})).error)
    def test_thread_must_be_first(self): self.assertIn("ordering", parse_codex_jsonl(json.dumps({"type":"turn.started"})).error)
    def test_duplicate_thread_rejected(self):
        line=json.dumps({"type":"thread.started","thread_id":"t"})
        self.assertIn("thread.started", parse_codex_jsonl(line+"\n"+line).error)
    def test_item_requires_turn(self):
        text=json.dumps({"type":"thread.started","thread_id":"t"})+"\n"+json.dumps({"type":"item.completed","item":{}})
        self.assertIn("item", parse_codex_jsonl(text).error)
    def test_event_after_terminal_rejected(self):
        self.assertIn("follows terminal", parse_codex_jsonl(success_jsonl()+"\n"+json.dumps({"type":"error","message":"late"})).error)
    def test_stdout_bound(self): self.assertIn("exceeds", parse_codex_jsonl("x"*(MAX_STDOUT_BYTES+1)).error)
    def test_event_count_bound(self):
        text="\n".join(json.dumps({"type":"error","message":"x"}) for _ in range(MAX_JSONL_EVENTS+1))
        self.assertIn("count", parse_codex_jsonl(text).error)


class ResultTests(unittest.TestCase):
    def test_success_schema_valid(self): self.assertIsNotNone(validate_final_output(final_output())[0])
    def test_failed_requires_error_fields(self):
        data=json.loads(final_output("FAILED")); data["error_code"]=None
        self.assertIn("requires", validate_final_output(json.dumps(data))[1])
    def test_success_rejects_error_fields(self):
        data=json.loads(final_output()); data["error_code"]="BAD"
        self.assertIn("cannot", validate_final_output(json.dumps(data))[1])
    def test_extra_field_rejected(self):
        data=json.loads(final_output()); data["extra"]=1
        self.assertIn("fields", validate_final_output(json.dumps(data))[1])
    def test_exit_zero_without_structured_result_is_not_verified(self):
        result=CodexProcessResult(1,0,"not json","","")
        self.assertFalse(verify_process_result(result).valid)
    def test_valid_nonzero_retains_invocation_failure(self):
        result=CodexProcessResult(1,7,success_jsonl(),"",final_output())
        verified=verify_process_result(result)
        self.assertTrue(verified.valid); self.assertFalse(verified.process_exit_success); self.assertIsNotNone(verified.error)
    def test_terminal_result_conflict_rejected(self):
        result=CodexProcessResult(1,0,failed_jsonl(),"",final_output())
        self.assertIn("conflict", verify_process_result(result).error)


class ExecutionTests(AdapterFixture):
    def test_default_adapter_has_no_workload_capability(self):
        with self.assertRaises(CodexExecutionNotAuthorizedError): self.execute(self.adapter())
    def test_cancelled_before_start_never_spawns(self):
        process=FakeProcess(); out=self.execute(self.adapter(process), cancelled=True)
        self.assertEqual(out.record.terminal_state,"CANCELLED"); self.assertEqual(process.starts,0)
    def test_revoked_before_start_never_spawns(self):
        process=FakeProcess(); out=self.execute(self.adapter(process), revoked=True)
        self.assertEqual(out.record.cancellation_reason,"LEASE_REVOKED_BEFORE_EXECUTION"); self.assertEqual(process.starts,0)
    def test_successful_fake_process_is_verified(self):
        result=CodexProcessResult(421,0,success_jsonl(),"",final_output())
        process=FakeProcess([result]); out=self.execute(self.adapter(process))
        self.assertEqual(out.record.start_state,"DEFINITELY_STARTED"); self.assertEqual(out.record.terminal_state,"VERIFIED")
        self.assertTrue(out.verified_result.valid); self.assertEqual(process.starts,1)
    def test_nonzero_with_pid_was_definitely_started(self):
        result=CodexProcessResult(421,9,success_jsonl(),"",final_output())
        out=self.execute(self.adapter(FakeProcess([result])))
        self.assertEqual(out.record.start_state,"DEFINITELY_STARTED"); self.assertTrue(out.process_started)
    def test_start_failure_is_definitive_before_start(self):
        out=self.execute(self.adapter(FakeProcess(start_error=OSError("no start"))))
        self.assertEqual(out.record.terminal_state,"FAILED_BEFORE_START"); self.assertFalse(out.process_started)
    def test_ambiguous_start_is_unknown(self):
        out=self.execute(self.adapter(FakeProcess(start_error=CodexStartStateUnknownError("lost ack"))))
        self.assertEqual(out.record.start_state,"UNKNOWN"); self.assertIsNone(out.record.terminal_state)
    def test_unknown_replay_never_spawns_again(self):
        process=FakeProcess(start_error=CodexStartStateUnknownError("lost")); adapter=self.adapter(process)
        self.execute(adapter); process.start_error=None; out=self.execute(adapter)
        self.assertTrue(out.replayed); self.assertEqual(process.starts,1)
    def test_terminal_replay_returns_same_run_without_spawn(self):
        result=CodexProcessResult(421,0,success_jsonl(),"",final_output()); process=FakeProcess([result]); adapter=self.adapter(process)
        first=self.execute(adapter); second=self.execute(adapter)
        self.assertEqual(first.record.runtime_run_id,second.record.runtime_run_id); self.assertEqual(process.starts,1)
        self.assertTrue(second.verified_result.valid)
    def test_failed_terminal_replay_never_spawns_again(self):
        result=CodexProcessResult(421,2,"","parser rejected argv",""); process=FakeProcess([result]); adapter=self.adapter(process)
        first=self.execute(adapter); second=self.execute(adapter)
        self.assertEqual(first.record.start_state,"DEFINITELY_STARTED"); self.assertEqual(first.record.terminal_state,"FAILED")
        self.assertTrue(second.replayed); self.assertEqual(second.record,first.record); self.assertEqual(process.starts,1)
    def test_divergent_replay_fails_closed(self):
        adapter=self.adapter(FakeProcess([CodexProcessResult(421,0,success_jsonl(),"",final_output())]))
        self.execute(adapter)
        with self.assertRaises(CodexReplayConflictError): self.execute(adapter, stdin_data='{"different":true}')
    def test_timeout_terminates_then_kills(self):
        clock=Clock(); process=FakeProcess(); out=self.execute(self.adapter(process, clock=clock))
        self.assertEqual(out.record.terminal_state,"TIMED_OUT"); self.assertEqual(process.terminates,1); self.assertEqual(process.kills,1)
    def test_cancellation_after_start_terminates_then_kills(self):
        process=FakeProcess(); out=self.execute(self.adapter(process), cancellation_check=lambda:"DELEGATION_CANCELLED")
        self.assertEqual(out.record.terminal_state,"CANCELLED"); self.assertEqual(process.terminates,1); self.assertEqual(process.kills,1)
    def test_durable_cancellation_after_start_is_observed(self):
        process=FakeProcess(); adapter=self.adapter(process); calls=0
        def cancel_once():
            nonlocal calls
            calls += 1
            if calls == 1: adapter.request_cancellation("idem-1","LEASE_REVOKED_DURING_EXECUTION")
            return None
        out=self.execute(adapter,cancellation_check=cancel_once)
        self.assertEqual(out.record.terminal_state,"CANCELLED")
        self.assertEqual(out.record.cancellation_reason,"LEASE_REVOKED_DURING_EXECUTION")
        self.assertEqual(process.starts,1)
    def test_repeated_cancellation_is_idempotent(self):
        adapter=self.adapter(FakeProcess()); record,_,_=adapter.prepare_invocation(idempotency_key="idem-1",launch_attempt_id="launch-1",delegation_id="delegation-1",stdin_data="{}")
        first=adapter.request_cancellation("idem-1","CANCELLED"); second=adapter.request_cancellation("idem-1","CANCELLED")
        self.assertEqual(first,second); self.assertEqual(second.terminal_state,"CANCELLED")
    def test_pid_mismatch_becomes_unknown(self):
        out=self.execute(self.adapter(FakeProcess([CodexProcessResult(999,0,success_jsonl(),"",final_output())])))
        self.assertEqual(out.record.start_state,"UNKNOWN"); self.assertIsNone(out.record.terminal_state)
    def test_prepared_replay_can_start_once(self):
        process=FakeProcess([CodexProcessResult(421,0,success_jsonl(),"",final_output())]); adapter=self.adapter(process)
        adapter.prepare_invocation(idempotency_key="idem-1",launch_attempt_id="launch-1",delegation_id="delegation-1",stdin_data='{"task":"read-only"}')
        out=self.execute(adapter); self.assertTrue(out.replayed); self.assertEqual(process.starts,1); self.assertEqual(out.record.terminal_state,"VERIFIED")
    def test_registry_survives_adapter_reconstruction(self):
        result=CodexProcessResult(421,0,success_jsonl(),"",final_output()); first=self.adapter(FakeProcess([result])); done=self.execute(first)
        second_process=FakeProcess(); replay=self.execute(self.adapter(second_process))
        self.assertEqual(done.record.runtime_run_id,replay.record.runtime_run_id); self.assertEqual(second_process.starts,0)
        self.assertTrue(replay.verified_result.valid)
    def test_registry_schema_mismatch_fails_closed(self):
        adapter=self.adapter(); adapter.registry.initialize()
        conn=sqlite3.connect(self.config.registry_path)
        try:
            conn.execute("UPDATE codex_transport_metadata SET schema_version=99")
            conn.commit()
        finally: conn.close()
        with self.assertRaises(CodexAdapterError):
            adapter.prepare_invocation(idempotency_key="idem-1",launch_attempt_id="launch-1",
                delegation_id="delegation-1",stdin_data="{}")
    def test_same_key_different_launch_conflicts(self):
        adapter=self.adapter(FakeProcess([CodexProcessResult(421,0,success_jsonl(),"",final_output())])); self.execute(adapter)
        with self.assertRaises(CodexReplayConflictError): self.execute(adapter, launch_attempt_id="launch-2")
    def test_start_state_nonzero_result_is_started(self):
        adapter=self.adapter(); result=CodexProcessResult(123,1,"","err")
        self.assertEqual(adapter.classify_start_state(123,result).state,"DEFINITELY_STARTED")
    def test_runtime_identity_is_distinct_from_governance_identities(self):
        adapter=self.adapter(); record,_,_=adapter.prepare_invocation(idempotency_key="idem-1",
            launch_attempt_id="launch-1",delegation_id="delegation-1",stdin_data="{}")
        for other in ("idem-1","launch-1","delegation-1","authorization-1","attempt-1","receipt-1","result-1"):
            self.assertNotEqual(record.runtime_run_id,other)
    def test_qualification_report_states_no_model_execution(self):
        report=self.adapter().qualify_no_live_invocation()
        self.assertFalse(report["live_invocation"]); self.assertFalse(report["model_agent_execution_possible"])
        self.assertEqual(report["approval_policy"], "never"); self.assertEqual(report["sandbox_policy"], "read-only")
        self.assertFalse(report["human_approval_prompts"]); self.assertFalse(report["automatic_operation_approval"])
        self.assertFalse(report["parser_output_artifact_changed"])
        self.assertEqual(report["binary_sha256"],self.config.expected_sha256); self.assertNotIn("PATH",report["environment_names"])
        self.assertEqual(report["cli_contract_id"], self.config.expected_cli_contract_id)
        self.assertEqual(self.parser_probes, 1)
    def test_parser_rejection_fails_qualification(self):
        adapter=CodexReceiverAdapter(config=self.config, version_probe=self.probe,
            parser_probe=lambda *_:(2,"","old ordering rejected"))
        with self.assertRaises(ArgvConstructionError): adapter.qualify_no_live_invocation()


class CapabilityAuditTests(unittest.TestCase):
    def test_no_prohibited_runtime_dependencies(self):
        import tools.hermes_core.codex_adapter as module
        source=Path(module.__file__).read_text(encoding="utf-8").lower()
        for token in ("comfyui", "regional_hand_repair", "studio bible", "kilo", "selenium", "playwright", "requests.", "socket."):
            self.assertNotIn(token,source)
    def test_metadata_probe_is_not_codex_exec(self):
        import inspect, tools.hermes_core.codex_adapter as module
        source=inspect.getsource(module._version_probe)
        self.assertIn('"--version"',source); self.assertNotIn('"exec"',source); self.assertIn("shell=False",source)


if __name__ == "__main__": unittest.main()
