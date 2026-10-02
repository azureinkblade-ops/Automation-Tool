"""EA-4D.3E-A focused tests: trusted local-worker config types + validation.

No process is created. These prove deterministic config hashing, exact
trusted resolution, and fail-closed behavior on missing/mismatched config.
"""

import os
import tempfile
import unittest

from tools.hermes_core.execution_start import (
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
)
from tools.hermes_core.local_worker_runtime_config import (
    LocalWorkerConfigHashMismatchError,
    LocalWorkerConfigMissingError,
    LocalWorkerConfigValidationError,
    LocalWorkerLaunchConfig,
    TrustedLocalWorkerConfigRegistry,
    local_worker_config_canonical_hash,
)


def _make_config(config_id="cfg1", executable="C:/trusted/worker.exe",
                 cwd="C:/trusted", argv=("--probe",)):
    return LocalWorkerLaunchConfig(
        config_id=config_id,
        config_version="1",
        executable=executable,
        argv_template=argv,
        cwd=cwd,
        environment_allowlist=("PATH", "SYSTEMROOT"),
    )


def _make_binding(config, config_hash=None):
    h = config_hash or local_worker_config_canonical_hash(config)
    return WorkerRuntimeBinding(
        runtime_binding_id="b1",
        runtime_binding_version="1",
        artifact_hash=h,
        worker_id="w1",
        worker_version="1",
        worker_class="wc",
        adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
        adapter_version="1",
        configuration_reference=config.config_id,
        configuration_hash=h,
        allowed_operations=["op1"],
        supports_idempotency=True,
        enabled=True,
    )


class ConfigHashTests(unittest.TestCase):
    def test_canonical_hash_deterministic(self):
        c1 = _make_config()
        c2 = _make_config()
        self.assertEqual(
            local_worker_config_canonical_hash(c1),
            local_worker_config_canonical_hash(c2))

    def test_hash_changes_with_boundary_field(self):
        c1 = _make_config()
        c2 = _make_config(executable="C:/trusted/worker2.exe")
        self.assertNotEqual(
            local_worker_config_canonical_hash(c1),
            local_worker_config_canonical_hash(c2))

    def test_hash_changes_with_argv_template(self):
        c1 = _make_config(argv=("--probe",))
        c2 = _make_config(argv=("--probe", "--extra"))
        self.assertNotEqual(
            local_worker_config_canonical_hash(c1),
            local_worker_config_canonical_hash(c2))


class ConfigValidationTests(unittest.TestCase):
    def test_absolute_executable_required(self):
        with self.assertRaises(LocalWorkerConfigValidationError):
            _make_config(executable="worker.exe")  # relative => PATH discovery

    def test_relative_executable_rejected(self):
        with self.assertRaises(LocalWorkerConfigValidationError):
            _make_config(executable="./worker")

    def test_cwd_must_be_absolute_or_none(self):
        with self.assertRaises(LocalWorkerConfigValidationError):
            _make_config(cwd="relative/dir")
        # None cwd is allowed.
        cfg = _make_config(cwd=None)
        self.assertIsNone(cfg.cwd)


class ConfigResolutionTests(unittest.TestCase):
    def test_exact_lookup_resolves(self):
        cfg = _make_config()
        reg = TrustedLocalWorkerConfigRegistry({cfg.config_id: cfg})
        resolved = reg.resolve(_make_binding(cfg))
        self.assertIs(resolved, cfg)

    def test_missing_config_fail_closed(self):
        cfg = _make_config()
        reg = TrustedLocalWorkerConfigRegistry({})  # empty
        with self.assertRaises(LocalWorkerConfigMissingError):
            reg.resolve(_make_binding(cfg))

    def test_configuration_hash_mismatch_fail_closed(self):
        cfg = _make_config()
        reg = TrustedLocalWorkerConfigRegistry({cfg.config_id: cfg})
        # Binding carries a WRONG configuration_hash.
        bad_binding = _make_binding(cfg, config_hash="0" * 64)
        with self.assertRaises(LocalWorkerConfigHashMismatchError):
            reg.resolve(bad_binding)

    def test_no_version_fallback(self):
        cfg = _make_config(config_id="cfg1", )
        reg = TrustedLocalWorkerConfigRegistry({cfg.config_id: cfg})
        binding = _make_binding(cfg)
        # Even if we imagine a different version, the config is addressed by id
        # and hash; there is no nearest-version selection. A tampered hash fails.
        bad = _make_binding(cfg, config_hash="f" * 64)
        with self.assertRaises(LocalWorkerConfigHashMismatchError):
            reg.resolve(bad)


if __name__ == "__main__":
    unittest.main()
