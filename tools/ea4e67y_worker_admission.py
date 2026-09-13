"""Test-owned, non-launching admission for the frozen local worker workload."""

import hashlib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"C:\Users\David\Documents\Automation tool\.venv-stage2-v2\Scripts\python.exe")
HELPER = ROOT / "tests/hermes_core/fixtures/local_worker_stub.py"
PYTHON_SHA256 = "0a864203aee170314ece97beaad6e50e226e76f0a3d73380a93ec472ed74f040"
HELPER_SHA256 = "622547fb220f7cb1069aea7580b71321b22132cc480e3b410e2a0910e418eff0"
WORKER = "tests/hermes_core/test_local_worker_runtime_adapter_process.py::"
COORDINATOR = "tests/hermes_core/test_execution_launch_coordinator_real_probe.py::RealCoordinatorProbeTests::"
FLAGS = {
    WORKER + "RealSpawnTests::test_valid_probe_returns_started": (),
    WORKER + "RealSpawnTests::test_worker_reject_returns_failed": ("--reject",),
    WORKER + "RealSpawnTests::test_exit_before_ack_recovers_started": ("--exit-before-ack",),
    WORKER + "RealSpawnTests::test_malformed_ack_recovers_started": ("--malformed-ack",),
    WORKER + "RealSpawnTests::test_post_delivery_pre_accept_ambiguity_is_unknown": ("--exit-before-commit",),
    WORKER + "RealSpawnTests::test_late_ack_exceeding_timeout_is_unknown": ("--sleep-before-commit", "1.5"),
    WORKER + "TimeoutMechanicsTests::test_ack_timeout_terminates_only_owned_child": ("--sleep-before-commit", "5"),
    WORKER + "TimeoutMechanicsTests::test_started_committed_before_timeout_recovers_found_started": ("--exit-before-ack", "--sleep", "1.5"),
    WORKER + "TimeoutMechanicsTests::test_synchronous_creation_yields_handle_or_definitive_failure": (),
    WORKER + "ReplayTests::test_same_key_replay_one_logical_row": (),
    WORKER + "ReplayTests::test_lookup_found_started_after_spawn": (),
    COORDINATOR + "test_explicit_real_coordinator_drives_probe": (),
    COORDINATOR + "test_real_coordinator_reconciles_after_spawn": (),
}
BUDGETS = {node: 2 if node.endswith("test_same_key_replay_one_logical_row") else 1 for node in FLAGS}
PROCESS_BUDGET = sum(BUDGETS.values())


def validate_worker_launch(node, argv, cwd, environment, basetemp, admitted):
    """Validate only; callers must separately govern launch and child cleanup."""
    if node not in FLAGS:
        raise ValueError("unauthorized node")
    if any(key not in BUDGETS or type(count) is not int or count < 0 or count > BUDGETS[key]
           for key, count in admitted.items()):
        raise ValueError("invalid admission accounting")
    if admitted.get(node, 0) >= BUDGETS[node] or sum(admitted.values()) >= PROCESS_BUDGET:
        raise ValueError("process budget exhausted")
    if not isinstance(argv, list) or len(argv) != 3 + len(FLAGS[node]):
        raise ValueError("unexpected argv")
    if Path(argv[0]).resolve() != PYTHON.resolve() or Path(argv[1]).resolve() != HELPER.resolve():
        raise ValueError("unqualified executable or helper")
    if tuple(argv[2:-1]) != FLAGS[node]:
        raise ValueError("unexpected fault flags")
    for path, digest in ((PYTHON, PYTHON_SHA256), (HELPER, HELPER_SHA256)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("frozen identity mismatch")
    base = Path(basetemp).resolve()
    if base == ROOT or not base.is_relative_to(ROOT) or not base.is_dir():
        raise ValueError("invalid temporary root")
    raw_state = Path(argv[-1])
    if not raw_state.is_absolute() or ".." in raw_state.parts or any(":" in part for part in raw_state.parts[1:]):
        raise ValueError("invalid state path")
    state = raw_state.resolve()
    if not state.is_relative_to(base) or state.suffix not in {".sqlite", ".sqlite3"}:
        raise ValueError("state outside temporary root")
    if Path(cwd).resolve() != ROOT:
        raise ValueError("unexpected cwd")
    if set(environment) - {"SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP"}:
        raise ValueError("unexpected environment")
    if any(environment[key] != os.environ.get(key) for key in ("SYSTEMROOT", "SYSTEMDRIVE") if key in environment):
        raise ValueError("unexpected system environment")
    for key in ("TEMP", "TMP"):
        if key not in environment or not Path(environment[key]).resolve().is_relative_to(base):
            raise ValueError("temporary environment outside root")
    return state
