"""EA-4D.3E-B focused tests: dry-run command construction, protocol parsing,
and the adapter's no-spawn boundary.

Reuses the proven EA-4D.3B canonical-chain fixture helpers. No process is
created: the adapter's ``launch()`` validates and builds the exact command, then
raises ``RuntimeAdapterExecutionNotAuthorizedError`` at the spawn boundary.
"""

import os
import shutil
import tempfile
import unittest

from tests.hermes_core.test_execution_launch_admission import (  # noqa: E402
    _build_canonical_chain,
    _persist_canonical_chain,
    _make_reservation,
    _persist_reservation,
    _make_binding_registry,
    _launcher_actor,
    _fresh_authority_db,
    _fresh_start_db,
    admit_execution_launch_attempt,
)
from tools.hermes_core.execution_start import (  # noqa: E402
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
)
from tools.hermes_core.local_worker_runtime_config import (  # noqa: E402
    LocalWorkerLaunchConfig,
    TrustedLocalWorkerConfigRegistry,
    local_worker_config_canonical_hash,
)
from tools.hermes_core.local_worker_runtime_adapter import (  # noqa: E402
    LocalWorkerRuntimeAdapter,
    LocalWorkerIdempotencyRegistry,
    RuntimeAdapterExecutionNotAuthorizedError,
    RuntimeAdapterValidationError,
    UnusableAcknowledgement,
    build_launch_command,
    parse_acknowledgement,
)
from tools.hermes_core.runtime_launch_adapter import (  # noqa: E402
    RuntimeLaunchOutcome,
)


def _make_config(config_id="cfg-probe"):
    return LocalWorkerLaunchConfig(
        config_id=config_id,
        config_version="1",
        executable="C:/trusted/worker.exe",
        argv_template=("--probe",),
        cwd="C:/trusted",
        environment_allowlist=("SYSTEMROOT",),
    )


def _probe_ack(idempotency_key, launch_attempt_id, runtime_run_id="run-abc"):
    import json
    return json.dumps({
        "protocol_version": "hermes-local-worker-v1",
        "idempotency_key": idempotency_key,
        "launch_attempt_id": launch_attempt_id,
        "runtime_run_id": runtime_run_id,
        "state": "STARTED",
    })


class AdapterFixture(unittest.TestCase):
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        self.chain = _build_canonical_chain(seed="3eb")
        _persist_canonical_chain(self.auth_store, self.chain)
        launcher = _launcher_actor()
        self.reservation = _make_reservation(
            self.chain, launcher_actor=launcher)
        _persist_reservation(
            self.start_store, self.reservation,
            now=self.reservation.reserved_at,
            must_start_by=self.reservation.must_start_by,
        )
        self.registry = _make_binding_registry(self.chain)
        self.attempt = admit_execution_launch_attempt(
            authority_store=self.auth_store,
            start_store=self.start_store,
            binding_registry=self.registry,
            reservation_id=self.reservation.reservation_id,
            launcher_actor=launcher,
        )
        # Build a binding consistent with the admitted attempt's immutable
        # snapshot, referencing the trusted config. This fully controls the
        # adapter boundary without depending on the 3B-chain binding's
        # unrelated configuration_hash.
        self.config = _make_config(config_id="hermes-worker-local-v1")
        self.config_registry = TrustedLocalWorkerConfigRegistry(
            {self.config.config_id: self.config})
        self.binding = WorkerRuntimeBinding(
            runtime_binding_id=self.attempt.runtime_binding_id,
            runtime_binding_version=self.attempt.runtime_binding_version,
            artifact_hash=self.attempt.runtime_binding_hash,
            worker_id=self.attempt.worker_id,
            worker_version=self.attempt.worker_version,
            worker_class=self.attempt.worker_class,
            adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
            adapter_version="1",
            configuration_reference=self.config.config_id,
            configuration_hash=local_worker_config_canonical_hash(self.config),
            allowed_operations=(self.attempt.operation,),
            supports_idempotency=True,
            enabled=True,
        )
        self.idem_tmp = tempfile.mkdtemp()
        self.idem_db = os.path.join(self.idem_tmp, "idem.sqlite")
        self.idem_registry = LocalWorkerIdempotencyRegistry(self.idem_db)
        self.idem_registry.initialize()
        self.adapter = LocalWorkerRuntimeAdapter(
            config_registry=self.config_registry,
            idempotency_registry=self.idem_registry,
        )

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)
        shutil.rmtree(self.idem_tmp, ignore_errors=True)


class DryRunCommandTests(AdapterFixture):
    def test_absolute_trusted_executable(self):
        cmd = build_launch_command(
            launch_attempt=self.attempt, binding=self.binding,
            config=self.config)
        self.assertEqual(cmd.executable, "C:/trusted/worker.exe")

    def test_shell_false_and_list_argv(self):
        cmd = build_launch_command(
            launch_attempt=self.attempt, binding=self.binding,
            config=self.config)
        self.assertIs(cmd.shell, False)
        self.assertIsInstance(cmd.argv, tuple)
        self.assertEqual(cmd.argv[0], "C:/trusted/worker.exe")
        self.assertEqual(cmd.argv[1:], ("--probe",))
        cmd.assert_no_shell()

    def test_trusted_cwd(self):
        cmd = build_launch_command(
            launch_attempt=self.attempt, binding=self.binding,
            config=self.config)
        self.assertEqual(cmd.cwd, "C:/trusted")

    def test_environment_allowlist(self):
        cmd = build_launch_command(
            launch_attempt=self.attempt, binding=self.binding,
            config=self.config)
        names = {name for name, _ in cmd.environment}
        self.assertEqual(names, {"SYSTEMROOT"})

    def test_canonical_request_serialization(self):
        cmd = build_launch_command(
            launch_attempt=self.attempt, binding=self.binding,
            config=self.config)
        import json
        payload = json.loads(cmd.request_payload_json)
        self.assertEqual(payload["protocol_version"], "hermes-local-worker-v1")
        self.assertEqual(payload["idempotency_key"], self.attempt.idempotency_key)
        self.assertEqual(payload["launch_attempt_id"], self.attempt.launch_attempt_id)
        self.assertEqual(payload["operation"], self.attempt.operation)

    def test_no_task_controlled_command_structure(self):
        # The argv is entirely from trusted config regardless of attempt data.
        cmd = build_launch_command(
            launch_attempt=self.attempt, binding=self.binding,
            config=self.config)
        self.assertEqual(cmd.argv, ("C:/trusted/worker.exe", "--probe"))


class ProtocolParsingTests(unittest.TestCase):
    def test_valid_started_ack(self):
        ack = parse_acknowledgement(_probe_ack("k1", "a1", "run-1"))
        self.assertEqual(ack.state, "STARTED")
        self.assertEqual(ack.runtime_run_id, "run-1")

    def test_wrong_protocol_rejected(self):
        import json
        bad = json.dumps({"protocol_version": "v0", "idempotency_key": "k",
                          "launch_attempt_id": "a", "runtime_run_id": "r",
                          "state": "STARTED"})
        with self.assertRaises(UnusableAcknowledgement):
            parse_acknowledgement(bad)

    def test_wrong_idempotency_key_rejected(self):
        with self.assertRaises(UnusableAcknowledgement):
            parse_acknowledgement(_probe_ack("", "a1"))

    def test_wrong_launch_attempt_id_rejected(self):
        with self.assertRaises(UnusableAcknowledgement):
            parse_acknowledgement(_probe_ack("k1", ""))

    def test_empty_runtime_run_id_rejected(self):
        with self.assertRaises(UnusableAcknowledgement):
            parse_acknowledgement(_probe_ack("k1", "a1", ""))

    def test_non_started_state_rejected(self):
        with self.assertRaises(UnusableAcknowledgement):
            parse_acknowledgement(_probe_ack("k1", "a1", "r").replace(
                '"state": "STARTED"', '"state": "MAYBE"'))

    def test_malformed_ack_normalizes_unusable(self):
        with self.assertRaises(UnusableAcknowledgement):
            parse_acknowledgement("not json at all")


class AdapterNoSpawnBoundaryTests(AdapterFixture):
    def test_launch_reaches_spawn_boundary_without_executing(self):
        with self.assertRaises(RuntimeAdapterExecutionNotAuthorizedError):
            self.adapter.launch(
                binding=self.binding,
                launch_attempt=self.attempt,
                idempotency_key=self.attempt.idempotency_key)

    def test_disabled_binding_fail_closed(self):
        bad = self._mutate_binding(enabled=False)
        with self.assertRaises(RuntimeAdapterValidationError):
            self.adapter.launch(
                binding=bad, launch_attempt=self.attempt,
                idempotency_key=self.attempt.idempotency_key)

    def test_operation_not_allowed_fail_closed(self):
        bad = self._mutate_binding(allowed_operations=("other-op",))
        with self.assertRaises(RuntimeAdapterValidationError):
            self.adapter.launch(
                binding=bad, launch_attempt=self.attempt,
                idempotency_key=self.attempt.idempotency_key)

    def test_idempotency_disabled_fail_closed(self):
        bad = self._mutate_binding(supports_idempotency=False)
        with self.assertRaises(RuntimeAdapterValidationError):
            self.adapter.launch(
                binding=bad, launch_attempt=self.attempt,
                idempotency_key=self.attempt.idempotency_key)

    def test_idempotency_key_mismatch_fail_closed(self):
        with self.assertRaises(RuntimeAdapterValidationError):
            self.adapter.launch(
                binding=self.binding,
                launch_attempt=self.attempt,
                idempotency_key="wrong-key")

    def test_binding_snapshot_mismatch_fail_closed(self):
        bad = self._mutate_binding(artifact_hash="0" * 64)
        with self.assertRaises(RuntimeAdapterValidationError):
            self.adapter.launch(
                binding=bad, launch_attempt=self.attempt,
                idempotency_key=self.attempt.idempotency_key)

    def test_non_local_adapter_kind_rejected(self):
        bad = self._mutate_binding(
            adapter_kind=WorkerRuntimeAdapterKind.HTTP_WORKER_ADAPTER)
        with self.assertRaises(RuntimeAdapterValidationError):
            self.adapter.launch(
                binding=bad, launch_attempt=self.attempt,
                idempotency_key=self.attempt.idempotency_key)

    def test_config_hash_mismatch_fail_closed(self):
        bad_config = _make_config()
        reg = TrustedLocalWorkerConfigRegistry({bad_config.config_id: bad_config})
        # Inject a registry whose config hash won't match the binding's stored
        # configuration_hash (binding was built against a different config).
        adapter = LocalWorkerRuntimeAdapter(
            config_registry=reg,
            idempotency_registry=self.idem_registry,
        )
        # Force the binding to reference this config id with a wrong hash.
        wrong_hash_binding = self._mutate_binding(
            configuration_reference=bad_config.config_id,
            configuration_hash="0" * 64)
        with self.assertRaises(RuntimeAdapterValidationError):
            adapter.launch(
                binding=wrong_hash_binding, launch_attempt=self.attempt,
                idempotency_key=self.attempt.idempotency_key)

    def _mutate_binding(self, **overrides):
        b = self.binding
        fields = {
            "runtime_binding_id": b.runtime_binding_id,
            "runtime_binding_version": b.runtime_binding_version,
            "artifact_hash": b.artifact_hash,
            "worker_id": b.worker_id,
            "worker_version": b.worker_version,
            "worker_class": b.worker_class,
            "adapter_kind": b.adapter_kind,
            "adapter_version": b.adapter_version,
            "configuration_reference": b.configuration_reference,
            "configuration_hash": b.configuration_hash,
            "allowed_operations": b.allowed_operations,
            "supports_idempotency": b.supports_idempotency,
            "enabled": b.enabled,
        }
        fields.update(overrides)
        return WorkerRuntimeBinding(**fields)


class CapabilityNegativeTests(unittest.TestCase):
    def test_no_executable_capability_in_production_modules(self):
        import ast
        base = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
        for mod in ("local_worker_runtime_adapter.py",
                    "local_worker_runtime_config.py"):
            path = os.path.join(base, "tools", "hermes_core", mod)
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            # Exact forbidden modules from the packet's capability gate.
            forbidden_imports = {
                "subprocess", "requests", "httpx", "urllib", "socket",
                "aiohttp", "playwright", "docker", "ssh", "paramiko",
                "fabric", "ollama",
            }
            forbidden_call_names = {
                "Popen", "requests", "httpx", "urllib", "Playwright",
                "Ollama", "Docker", "SSH", "PowerShell", "cmd", "bash",
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_imports:
                            self.fail(f"{mod}: forbidden import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    modname = (node.module or "").split(".")[0]
                    if modname in forbidden_imports:
                        self.fail(f"{mod}: forbidden import {modname}")
                elif isinstance(node, ast.Call):
                    # Prohibit os.system specifically (os module itself allowed
                    # for os.environ / os.path).
                    if (isinstance(node.func, ast.Attribute)
                            and node.func.attr == "system"
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"):
                        self.fail(f"{mod}: os.system call prohibited")
                    # Prohibit shell=True on any call (e.g. Popen).
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                            if kw.value.value is True:
                                self.fail(f"{mod}: shell=True call prohibited")
                    name = getattr(node.func, "attr", None) or getattr(
                        node.func, "id", None)
                    if name in forbidden_call_names:
                        self.fail(f"{mod}: forbidden call {name}")


if __name__ == "__main__":
    unittest.main()
