"""EA-4D.3A tests: trusted runtime-binding registry + deterministic resolver.

Pure tests only -- no persistence, no process/network, no adapter/worker
invocation. They exercise exact-identity resolution, fail-closed validation,
registry determinism/hashing, and capability-negative assertions.
"""

import ast
import os
import unittest

from tools.hermes_core.execution_start import (
    ExecutionRuntimeBindingIntegrityError,
    ExecutionRuntimeBindingMismatchError,
    ExecutionRuntimeBindingNotFoundError,
    WorkerRuntimeAdapterKind,
    build_worker_runtime_binding,
)
from tools.hermes_core.runtime_binding_registry import (
    build_worker_runtime_binding_registry,
    ExecutionRuntimeBindingDisabledError,
    ExecutionRuntimeBindingIdempotencyRequiredError,
    ExecutionRuntimeBindingRegistryConflictError,
    ExecutionRuntimeBindingRegistryError,
    resolve_worker_runtime_binding,
    WorkerRuntimeBindingRegistry,
    _is_shell_like_reference,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _binding(
    *,
    runtime_binding_id,
    worker_id,
    worker_version,
    worker_class="run-sandboxed",
    adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
    adapter_version="1",
    configuration_reference="hermes-worker-local-v1",
    configuration_hash="a" * 64,
    allowed_operations=("run-sandboxed",),
    supports_idempotency=True,
    enabled=True,
):
    return build_worker_runtime_binding(
        runtime_binding_id=runtime_binding_id,
        worker_id=worker_id,
        worker_version=worker_version,
        worker_class=worker_class,
        adapter_kind=adapter_kind,
        adapter_version=adapter_version,
        configuration_reference=configuration_reference,
        configuration_hash=configuration_hash,
        allowed_operations=list(allowed_operations),
        supports_idempotency=supports_idempotency,
        enabled=enabled,
    )


class RegistryConstructionTests(unittest.TestCase):
    def test_valid_registry_construction(self):
        a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        b = _binding(runtime_binding_id="b-b", worker_id="w-b", worker_version="v1")
        reg = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a, b]
        )
        self.assertTrue(reg.verify_hash())
        self.assertEqual(reg.registry_version, "1")
        self.assertEqual(len(reg.bindings), 2)

    def test_deterministic_registry_hash(self):
        a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        b = _binding(runtime_binding_id="b-b", worker_id="w-b", worker_version="v1")
        r1 = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a, b]
        )
        r2 = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[b, a]  # reversed input
        )
        self.assertEqual(r1.artifact_hash, r2.artifact_hash)
        self.assertEqual(r1.canonical_json(), r2.canonical_json())

    def test_reordered_bindings_same_hash(self):
        a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        b = _binding(runtime_binding_id="b-b", worker_id="w-b", worker_version="v1")
        c = _binding(runtime_binding_id="b-c", worker_id="w-c", worker_version="v1")
        forward = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a, b, c]
        )
        backward = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[c, b, a]
        )
        self.assertEqual(forward.artifact_hash, backward.artifact_hash)

    def test_binding_mutation_changes_hash(self):
        a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        b = _binding(runtime_binding_id="b-b", worker_id="w-b", worker_version="v1")
        base = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a, b]
        )
        b2 = _binding(
            runtime_binding_id="b-b", worker_id="w-b", worker_version="v1",
            adapter_version="2",
        )
        mutated = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a, b2]
        )
        self.assertNotEqual(base.artifact_hash, mutated.artifact_hash)

    def test_registry_version_changes_hash(self):
        a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        b = _binding(runtime_binding_id="b-b", worker_id="w-b", worker_version="v1")
        r1 = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a, b]
        )
        r2 = build_worker_runtime_binding_registry(
            registry_version="2", bindings=[a, b]
        )
        self.assertNotEqual(r1.artifact_hash, r2.artifact_hash)

    def test_duplicate_exact_identity_rejected(self):
        a1 = _binding(runtime_binding_id="b-a1", worker_id="w-a", worker_version="v1")
        a2 = _binding(runtime_binding_id="b-a2", worker_id="w-a", worker_version="v1")
        with self.assertRaises(ExecutionRuntimeBindingRegistryConflictError):
            build_worker_runtime_binding_registry(
                registry_version="1", bindings=[a1, a2]
            )

    def test_empty_registry_allowed(self):
        reg = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[]
        )
        self.assertTrue(reg.verify_hash())
        self.assertEqual(len(reg.bindings), 0)
        # Resolving anything from an empty registry must fail closed.
        with self.assertRaises(ExecutionRuntimeBindingNotFoundError):
            resolve_worker_runtime_binding(
                registry=reg, worker_id="w-a", worker_version="v1",
                worker_class="run-sandboxed", operation="run-sandboxed",
            )

    def test_invalid_binding_hash_rejected(self):
        from tools.hermes_core.execution_start import WorkerRuntimeBinding
        bad = WorkerRuntimeBinding(
            runtime_binding_id="b-bad",
            runtime_binding_version="1",
            artifact_hash="0" * 64,  # wrong hash
            worker_id="w-a",
            worker_version="v1",
            worker_class="run-sandboxed",
            adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
            adapter_version="1",
            configuration_reference="hermes-worker-local-v1",
            configuration_hash="a" * 64,
            allowed_operations=["run-sandboxed"],
            supports_idempotency=True,
            enabled=True,
        )
        with self.assertRaises(ExecutionRuntimeBindingIntegrityError):
            build_worker_runtime_binding_registry(
                registry_version="1", bindings=[bad]
            )

    def test_invalid_configuration_hash_rejected(self):
        a = _binding(
            runtime_binding_id="b-a", worker_id="w-a", worker_version="v1",
            configuration_hash="not-a-hash",
        )
        with self.assertRaises(ExecutionRuntimeBindingIntegrityError):
            build_worker_runtime_binding_registry(
                registry_version="1", bindings=[a]
            )

    def test_invalid_registry_hash_verify_failure(self):
        a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        reg = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a]
        )
        # Tamper the stored hash to break verify_hash().
        tampered = WorkerRuntimeBindingRegistry(
            registry_version=reg.registry_version,
            artifact_hash="0" * 64,
            bindings=reg.bindings,
            registration_source=reg.registration_source,
            registration_version=reg.registration_version,
        )
        self.assertFalse(tampered.verify_hash())
        with self.assertRaises(ExecutionRuntimeBindingRegistryError):
            resolve_worker_runtime_binding(
                registry=tampered, worker_id="w-a", worker_version="v1",
                worker_class="run-sandboxed", operation="run-sandboxed",
            )


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        self.b = _binding(runtime_binding_id="b-b", worker_id="w-b", worker_version="v1")
        self.reg = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[self.a, self.b]
        )

    def test_exact_worker_identity_resolves(self):
        out = resolve_worker_runtime_binding(
            registry=self.reg, worker_id="w-a", worker_version="v1",
            worker_class="run-sandboxed", operation="run-sandboxed",
        )
        self.assertEqual(out.runtime_binding_id, "b-a")

    def test_wrong_worker_id_not_found(self):
        with self.assertRaises(ExecutionRuntimeBindingNotFoundError):
            resolve_worker_runtime_binding(
                registry=self.reg, worker_id="w-z", worker_version="v1",
                worker_class="run-sandboxed", operation="run-sandboxed",
            )

    def test_wrong_worker_version_not_found(self):
        with self.assertRaises(ExecutionRuntimeBindingNotFoundError):
            resolve_worker_runtime_binding(
                registry=self.reg, worker_id="w-a", worker_version="v2",
                worker_class="run-sandboxed", operation="run-sandboxed",
            )

    def test_wrong_worker_class_not_found(self):
        with self.assertRaises(ExecutionRuntimeBindingNotFoundError):
            resolve_worker_runtime_binding(
                registry=self.reg, worker_id="w-a", worker_version="v1",
                worker_class="other-class", operation="run-sandboxed",
            )

    def test_operation_allowed_pass(self):
        out = resolve_worker_runtime_binding(
            registry=self.reg, worker_id="w-a", worker_version="v1",
            worker_class="run-sandboxed", operation="run-sandboxed",
        )
        self.assertEqual(out.runtime_binding_id, "b-a")

    def test_operation_not_allowed_fail(self):
        with self.assertRaises(ExecutionRuntimeBindingMismatchError):
            resolve_worker_runtime_binding(
                registry=self.reg, worker_id="w-a", worker_version="v1",
                worker_class="run-sandboxed", operation="forbidden-op",
            )

    def test_disabled_binding_typed_failure(self):
        d = _binding(
            runtime_binding_id="b-disabled", worker_id="w-d", worker_version="v1",
            enabled=False,
        )
        reg = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[d]
        )
        with self.assertRaises(ExecutionRuntimeBindingDisabledError):
            resolve_worker_runtime_binding(
                registry=reg, worker_id="w-d", worker_version="v1",
                worker_class="run-sandboxed", operation="run-sandboxed",
            )

    def test_supports_idempotency_false_typed_failure(self):
        ni = _binding(
            runtime_binding_id="b-noidem", worker_id="w-ni", worker_version="v1",
            supports_idempotency=False,
        )
        reg = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[ni]
        )
        with self.assertRaises(ExecutionRuntimeBindingIdempotencyRequiredError):
            resolve_worker_runtime_binding(
                registry=reg, worker_id="w-ni", worker_version="v1",
                worker_class="run-sandboxed", operation="run-sandboxed",
            )

    def test_unknown_adapter_kind_typed_failure(self):
        # adapter_kind that is not a valid enum member is rejected at build time.
        from tools.hermes_core.execution_start import WorkerRuntimeBinding
        bad = WorkerRuntimeBinding(
            runtime_binding_id="b-badkind", runtime_binding_version="1",
            artifact_hash="",
            worker_id="w-bk", worker_version="v1",
            worker_class="run-sandboxed",
            adapter_kind="NOT_A_REAL_KIND",  # invalid
            adapter_version="1",
            configuration_reference="hermes-worker-local-v1",
            configuration_hash="a" * 64,
            allowed_operations=["run-sandboxed"], supports_idempotency=True,
            enabled=True,
        )
        from tools.hermes_core.execution_start import ExecutionRuntimeBindingIntegrityError
        with self.assertRaises(ExecutionRuntimeBindingIntegrityError):
            build_worker_runtime_binding_registry(
                registry_version="1", bindings=[bad]
            )

    def test_empty_invalid_adapter_version_typed_failure(self):
        bad = _binding(
            runtime_binding_id="b-badver", worker_id="w-bv", worker_version="v1",
            adapter_version="",
        )
        with self.assertRaises(ExecutionRuntimeBindingIntegrityError):
            build_worker_runtime_binding_registry(
                registry_version="1", bindings=[bad]
            )

    def test_invalid_configuration_reference_typed_failure(self):
        for bad_ref in ("powershell -c evil", "bash -c rm -rf", "https://evil.example/run",
                        "/usr/bin/worker", "C:\\Windows\\System32\\worker.exe"):
            with self.subTest(bad_ref=bad_ref):
                bad = _binding(
                    runtime_binding_id="b-badref", worker_id="w-br",
                    worker_version="v1", configuration_reference=bad_ref,
                )
                with self.assertRaises(ExecutionRuntimeBindingIntegrityError):
                    build_worker_runtime_binding_registry(
                        registry_version="1", bindings=[bad]
                    )


class NoFallbackTests(unittest.TestCase):
    def test_no_fallback_to_another_worker(self):
        # Registry has A v1 and B v1. Request A v2 -> FAIL CLOSED, must not
        # return A v1 or B v1.
        a = _binding(runtime_binding_id="b-a", worker_id="w-a", worker_version="v1")
        b = _binding(runtime_binding_id="b-b", worker_id="w-b", worker_version="v1")
        reg = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[a, b]
        )
        with self.assertRaises(ExecutionRuntimeBindingNotFoundError):
            resolve_worker_runtime_binding(
                registry=reg, worker_id="w-a", worker_version="v2",
                worker_class="run-sandboxed", operation="run-sandboxed",
            )


class ConfigurationReferenceValidationTests(unittest.TestCase):
    def test_symbolic_reference_allowed(self):
        for ok in ("hermes-worker-local-v1", "ollama-runtime-primary-v2",
                   "render-node-profile-a-v3", "model-runtime-1"):
            with self.subTest(ok=ok):
                self.assertFalse(_is_shell_like_reference(ok))

    def test_shell_like_reference_rejected(self):
        for bad in ("", "powershell", "cmd.exe", "bash -c 'x'", "sh -c x",
                    "pwsh", "python -c 'x'", "http://host/x", "https://host/x",
                    "/bin/sh", "C:\\Windows\\System32\\cmd.exe"):
            with self.subTest(bad=bad):
                self.assertTrue(_is_shell_like_reference(bad))


class CapabilityNegativeTests(unittest.TestCase):
    def _read_module_source(self):
        import ast as _ast
        with open(
            os.path.join(REPO_ROOT, "tools", "hermes_core",
                         "runtime_binding_registry.py")
        ) as fh:
            src = fh.read()
        tree = _ast.parse(src)
        # Collect code-level identifiers/attributes (NOT docstring prose).
        used = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Name):
                used.add(node.id)
            elif isinstance(node, _ast.Attribute):
                used.add(node.attr)
        return src, used

    def test_module_does_not_import_worker_router_selection_apis(self):
        src, used = self._read_module_source()
        # The module must not reference WorkerRouter selection APIs as code.
        # (Prose mentions of the upstream WorkerRouteDecision artifact in the
        # module docstring are allowed per the EA-4D.3A packet.)
        forbidden = {
            "select_and_record_worker_route",
            "worker_router_service",
            "build_worker_route_decision",
        }
        leaked = {t for t in forbidden if t in used}
        self.assertEqual(leaked, set(),
                         f"module references router APIs: {leaked}")

    def test_module_has_no_invocation_capability_tokens(self):
        src, used = self._read_module_source()
        # None of these executable capabilities may appear as code identifiers.
        exec_tokens = {
            "subprocess", "Popen", "os", "socket", "requests", "httpx",
            "urllib", "sqlite3", "Playwright", "Ollama",
        }
        leaked = {t for t in exec_tokens if t in used}
        self.assertEqual(leaked, set(),
                         f"module contains executable tokens: {leaked}")
        # Prose mentions in docstrings are acceptable; verify no CALL to these.
        for token in ("subprocess", "Popen", "socket", "requests", "httpx",
                      "sqlite3"):
            self.assertNotIn(f"{token}(", src,
                              f"module must not call {token}()")


if __name__ == "__main__":
    unittest.main()
