"""EA-4D.3E-C real process-spawn tests: the deterministic local probe.

These exercise the REAL subprocess boundary (subprocess.Popen, shell=False)
against the authorized probe worker (fixtures/local_worker_stub.py). No
network, no user work, no model runtime. The worker writes to the worker-owned
SQLite registry; the adapter normalizes via authoritative lookup.

This file is the authorized EA-4D.3E-C process test surface, including the
timeout/locking correction mechanics required by the review.
"""

import os
import shutil
import sqlite3
import sys
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
from tools.hermes_core.local_worker_process_control import (
    LocalWorkerProcessControl,
    ProcessSpawnError,
)
from tools.hermes_core.local_worker_runtime_adapter import (  # noqa: E402
    LocalWorkerRuntimeAdapter,
    LocalWorkerIdempotencyRegistry,
    LocalWorkerTimeouts,
    RuntimeAdapterExecutionNotAuthorizedError,
)
from tools.hermes_core.runtime_launch_adapter import RuntimeLaunchOutcome


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROBE_SCRIPT = os.path.join(
    REPO_ROOT, "tests", "hermes_core", "fixtures", "local_worker_stub.py")


def _make_config(config_id, executable=sys.executable, cwd=None, extra_argv=()):
    return LocalWorkerLaunchConfig(
        config_id=config_id,
        config_version="1",
        executable=executable,
        argv_template=(PROBE_SCRIPT,) + tuple(extra_argv),
        cwd=cwd if cwd is not None else REPO_ROOT,
        environment_allowlist=("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP"),
    )


def _real_adapter(idem_db, timeouts, config=None, config_registry=None):
    if config is None:
        config = _make_config("hermes-worker-local-v1")
    if config_registry is None:
        config_registry = TrustedLocalWorkerConfigRegistry(
            {config.config_id: config})
    idem_registry = LocalWorkerIdempotencyRegistry(
        idem_db, lookup_timeout_seconds=timeouts.lookup_timeout_seconds)
    idem_registry.initialize()
    return LocalWorkerRuntimeAdapter(
        config_registry=config_registry,
        idempotency_registry=idem_registry,
        process_control=LocalWorkerProcessControl(),
        timeouts=timeouts,
    )


def _consistent_binding(attempt, config):
    return WorkerRuntimeBinding(
        runtime_binding_id=attempt.runtime_binding_id,
        runtime_binding_version=attempt.runtime_binding_version,
        artifact_hash=attempt.runtime_binding_hash,
        worker_id=attempt.worker_id,
        worker_version=attempt.worker_version,
        worker_class=attempt.worker_class,
        adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
        adapter_version="1",
        configuration_reference=config.config_id,
        configuration_hash=local_worker_config_canonical_hash(config),
        allowed_operations=(attempt.operation,),
        supports_idempotency=True,
        enabled=True,
    )


class RealSpawnFixture(unittest.TestCase):
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        self.chain = _build_canonical_chain(seed="3ec")
        _persist_canonical_chain(self.auth_store, self.chain)
        launcher = _launcher_actor()
        self.reservation = _make_reservation(self.chain, launcher_actor=launcher)
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
        self.config = _make_config("hermes-worker-local-v1")
        self.timeouts = LocalWorkerTimeouts(
            ack_timeout_seconds=5,
            lookup_timeout_seconds=2, shutdown_timeout_seconds=3)
        self.idem_tmp = tempfile.mkdtemp()
        self.idem_db = os.path.join(self.idem_tmp, "idem.sqlite")
        self.adapter = _real_adapter(self.idem_db, self.timeouts, self.config)
        self.binding = _consistent_binding(self.attempt, self.config)

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)
        shutil.rmtree(self.idem_tmp, ignore_errors=True)

    def _adapter_for_config(self, config, timeouts=None):
        return _real_adapter(
            self.idem_db, timeouts or self.timeouts, config,
            TrustedLocalWorkerConfigRegistry({config.config_id: config}))

    def _binding_for_config(self, config):
        return _consistent_binding(self.attempt, config)


class RealSpawnTests(RealSpawnFixture):
    def test_valid_probe_returns_started(self):
        res = self.adapter.launch(
            binding=self.binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)
        self.assertTrue(res.runtime_run_id)
        self.assertTrue(res.runtime_run_id.startswith("probe-run-"))

    def test_executable_missing_fails_closed(self):
        bad_config = _make_config(
            "hermes-worker-local-v1",
            executable="C:/does/not/exist/python.exe")
        adapter = self._adapter_for_config(bad_config)
        binding = self._binding_for_config(bad_config)
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.FAILED)
        self.assertEqual(res.error_code, "PROCESS_CREATION_FAILED")

    def test_worker_reject_returns_failed(self):
        cfg = _make_config("hermes-worker-local-v1", extra_argv=("--reject",))
        adapter = self._adapter_for_config(cfg)
        binding = self._binding_for_config(cfg)
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.FAILED)

    def test_exit_before_ack_recovers_started(self):
        # Worker commits STARTED to the registry, then exits without emitting a
        # usable ack. The adapter recovers STARTED authoritatively (Crash-F).
        cfg = _make_config("hermes-worker-local-v1",
                           extra_argv=("--exit-before-ack",))
        adapter = self._adapter_for_config(cfg)
        binding = self._binding_for_config(cfg)
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)

    def test_malformed_ack_recovers_started(self):
        # Worker commits STARTED, emits garbage. Registry is authoritative ->
        # STARTED recovered.
        cfg = _make_config("hermes-worker-local-v1",
                           extra_argv=("--malformed-ack",))
        adapter = self._adapter_for_config(cfg)
        binding = self._binding_for_config(cfg)
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)

    def test_post_delivery_pre_accept_ambiguity_is_unknown(self):
        # Worker validates then dies before committing -> no registry row ->
        # ambiguous -> UNKNOWN (NOT the same as Crash-F, which is post-accept).
        cfg = _make_config("hermes-worker-local-v1",
                           extra_argv=("--exit-before-commit",))
        adapter = self._adapter_for_config(cfg)
        binding = self._binding_for_config(cfg)
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)

    def test_late_ack_exceeding_timeout_is_unknown(self):
        # Child sleeps BEFORE committing (--sleep-before-commit) and stays
        # alive past ack_timeout. timeout must bound the I/O; no registry row
        # -> UNKNOWN, child killed.
        cfg = _make_config("hermes-worker-local-v1",
                           extra_argv=("--sleep-before-commit", "1.5"))
        adapter = self._adapter_for_config(
            cfg, LocalWorkerTimeouts(
                ack_timeout_seconds=0.3,
                lookup_timeout_seconds=2, shutdown_timeout_seconds=3))
        binding = self._binding_for_config(cfg)
        import time
        start = time.time()
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        elapsed = time.time() - start
        # Bounded: elapsed must be well under the child's 1.5s sleep.
        self.assertLess(elapsed, 1.2)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)
        # No acceptance row because the worker never reached _accept().
        conn = sqlite3.connect(self.idem_db, isolation_level=None)
        count = conn.execute(
            "SELECT COUNT(*) FROM local_worker_idempotency WHERE idempotency_key=?",
            (self.attempt.idempotency_key,)).fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)


class TimeoutMechanicsTests(RealSpawnFixture):
    def test_ack_timeout_terminates_only_owned_child(self):
        # A child that never commits and stays alive must be terminated by the
        # shutdown window, leaving no orphan and returning bounded UNKNOWN.
        cfg = _make_config("hermes-worker-local-v1",
                           extra_argv=("--sleep-before-commit", "5"))
        adapter = self._adapter_for_config(
            cfg, LocalWorkerTimeouts(
                ack_timeout_seconds=0.3,
                lookup_timeout_seconds=2, shutdown_timeout_seconds=1))
        binding = self._binding_for_config(cfg)
        import time
        start = time.time()
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        elapsed = time.time() - start
        # ack_timeout(0.3) + shutdown(1) bounded; child slept 5s but is killed.
        self.assertLess(elapsed, 2.0)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)

    def test_started_committed_before_timeout_recovers_found_started(self):
        # Worker commits STARTED then sleeps past ack_timeout. The adapter
        # times out the ack, but reconciliation recovers the authoritative row.
        cfg = _make_config(
            "hermes-worker-local-v1",
            extra_argv=("--exit-before-ack", "--sleep", "1.5"))
        adapter = self._adapter_for_config(
            cfg, LocalWorkerTimeouts(
                ack_timeout_seconds=0.3,
                lookup_timeout_seconds=2, shutdown_timeout_seconds=3))
        binding = self._binding_for_config(cfg)
        import time
        start = time.time()
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.2)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)

    def test_sqlite_lock_respects_lookup_bound_is_unknown(self):
        # Hold an EXCLUSIVE write lock on the registry (blocks the reader's
        # SHARED lock), then lookup() must fail bounded (busy_timeout) and
        # normalize to UNKNOWN rather than hang.
        conn = sqlite3.connect(self.idem_db, isolation_level=None, timeout=0)
        conn.execute("PRAGMA busy_timeout=0")
        conn.execute("BEGIN EXCLUSIVE")
        import time
        start = time.time()
        res = self.bound_lookup(self.attempt.idempotency_key)
        elapsed = time.time() - start
        conn.execute("ROLLBACK")
        conn.close()
        self.assertLess(elapsed, 1.5)
        from tools.hermes_core.runtime_launch_adapter import RuntimeLookupOutcome
        self.assertEqual(res.outcome, RuntimeLookupOutcome.UNKNOWN)

    def bound_lookup(self, key):
        reg = LocalWorkerIdempotencyRegistry(
            self.idem_db, lookup_timeout_seconds=0.2)
        return reg.lookup(key)

    def test_no_thread_wrapped_spawn_in_module(self):
        # The production process-control module must NOT wrap Popen in a
        # daemon/thread spawn timeout. Synchronous creation preserves the clean
        # pre-delivery-failure vs process-exists boundary; a thread join cannot
        # cancel Popen() and would create a duplicate-execution race.
        import inspect
        from tools.hermes_core import local_worker_process_control as pcm
        src = inspect.getsource(pcm)
        self.assertNotIn("threading.Thread", src)
        self.assertNotIn("_bounded_spawn", src)
        self.assertNotIn("spawn_timeout_seconds", src)
        # Exactly one synchronous Popen call site, shell=False.
        self.assertIn("subprocess.Popen", src)
        self.assertIn("shell=False", src)

    def test_synchronous_creation_yields_handle_or_definitive_failure(self):
        # Synchronous Popen: either a concrete process handle exists, or a
        # definitive construction exception is raised. There is no unsafe
        # in-between state where a process may appear later.
        import tests.hermes_core.test_local_worker_runtime_adapter_process as M
        from tools.hermes_core import local_worker_process_control as pcm
        from tools.hermes_core.local_worker_runtime_adapter import (
            LocalWorkerIdempotencyRegistry)
        db = os.path.join(self.idem_tmp, "idem_sync.sqlite")
        cfg = M._make_config("hermes-worker-local-v1")
        req = ('{"protocol_version":"hermes-local-worker-v1",'
               '"launch_attempt_id":"a","reservation_id":"r","route_id":"rt",'
               '"worker_id":"w","worker_version":"1","operation":"op",'
               '"input_hash":"h","idempotency_key":"k"}')
        # Missing executable -> synchronous definitive failure (no process).
        with self.assertRaises(pcm.ProcessSpawnError):
            pcm.spawn_probe(
                executable="C:/does/not/exist/python.exe",
                argv=cfg.argv_template,
                cwd=cfg.cwd,
                environment=tuple(
                    (n, os.environ.get(n, "")) for n in cfg.environment_allowlist),
                request_json=req,
                ack_timeout_seconds=2,
                shutdown_timeout_seconds=2)
        # Valid executable -> synchronous handle, real STARTED, clean exit.
        reg = LocalWorkerIdempotencyRegistry(db, lookup_timeout_seconds=2)
        reg.initialize()
        adapter = LocalWorkerRuntimeAdapter(
            config_registry=TrustedLocalWorkerConfigRegistry(
                {cfg.config_id: cfg}),
            idempotency_registry=reg,
            process_control=pcm.LocalWorkerProcessControl(),
            timeouts=LocalWorkerTimeouts(
                ack_timeout_seconds=2, lookup_timeout_seconds=2,
                shutdown_timeout_seconds=2))
        binding = M._consistent_binding(self.attempt, cfg)
        # Use a fresh attempt-like object is unnecessary; reuse self.attempt.
        res = adapter.launch(
            binding=binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)


class ReplayTests(RealSpawnFixture):
    def test_same_key_replay_one_logical_row(self):
        self.adapter.launch(
            binding=self.binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        self.adapter.launch(
            binding=self.binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        # The worker-owned registry must contain exactly one logical row.
        conn = sqlite3.connect(self.idem_db, isolation_level=None)
        count = conn.execute(
            "SELECT COUNT(*) FROM local_worker_idempotency WHERE idempotency_key = ?",
            (self.attempt.idempotency_key,)).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_lookup_found_started_after_spawn(self):
        self.adapter.launch(
            binding=self.binding, launch_attempt=self.attempt,
            idempotency_key=self.attempt.idempotency_key)
        res = self.adapter.lookup(self.attempt.idempotency_key)
        from tools.hermes_core.runtime_launch_adapter import RuntimeLookupOutcome
        self.assertEqual(res.outcome, RuntimeLookupOutcome.FOUND_STARTED)


class DryRunBoundaryStillHolds(unittest.TestCase):
    def test_no_process_control_raises_not_authorized(self):
        # A default-constructed adapter (no process_control) must still stop at
        # the dry-run boundary, preserving fake-only default behavior.
        from tests.hermes_core.test_execution_launch_admission import (
            _build_canonical_chain, _persist_canonical_chain, _make_reservation,
            _persist_reservation, _launcher_actor, _fresh_authority_db,
            _fresh_start_db, admit_execution_launch_attempt,
            _make_binding_registry,
        )
        auth_tmp, auth_store = _fresh_authority_db()
        start_tmp, start_store = _fresh_start_db()
        try:
            chain = _build_canonical_chain(seed="dry")
            _persist_canonical_chain(auth_store, chain)
            launcher = _launcher_actor()
            resv = _make_reservation(chain, launcher_actor=launcher)
            _persist_reservation(start_store, resv, now=resv.reserved_at,
                                 must_start_by=resv.must_start_by)
            reg = _make_binding_registry(chain)
            attempt = admit_execution_launch_attempt(
                authority_store=auth_store, start_store=start_store,
                binding_registry=reg, reservation_id=resv.reservation_id,
                launcher_actor=launcher)
            cfg = _make_config("hermes-worker-local-v1")
            binding = _consistent_binding(attempt, cfg)
            idem_tmp = tempfile.mkdtemp()
            try:
                idem_db = os.path.join(idem_tmp, "idem.sqlite")
                idem = LocalWorkerIdempotencyRegistry(idem_db)
                idem.initialize()
                adapter = LocalWorkerRuntimeAdapter(
                    config_registry=TrustedLocalWorkerConfigRegistry(
                        {cfg.config_id: cfg}),
                    idempotency_registry=idem)
                with self.assertRaises(RuntimeAdapterExecutionNotAuthorizedError):
                    adapter.launch(
                        binding=binding, launch_attempt=attempt,
                        idempotency_key=attempt.idempotency_key)
            finally:
                shutil.rmtree(idem_tmp, ignore_errors=True)
        finally:
            auth_store.close()
            start_store.close()
            shutil.rmtree(auth_tmp, ignore_errors=True)
            shutil.rmtree(start_tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
